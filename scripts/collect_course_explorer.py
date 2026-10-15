"""Collect a complete Course Explorer snapshot without writing published files."""

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from http.client import HTTPException
import json
import math
import ssl
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.data_contract import API_BASE, COURSE_PATTERN, TERMS, AccessDenied, DataError, RequestError, atomic_write_json, require, timestamp, validate_snapshot
from scripts.course_explorer_discovery import CourseExplorerDiscovery, historical_year, parse_xml

ROOT = Path(__file__).resolve().parents[1]
DIRECTIVE = re.compile(r"\b(Same as|See)\s+([A-Z][A-Z&]{1,9}\s+\d{2,3}[A-Z]?(?:\s*(?:,|and|/)\s*[A-Z][A-Z&]{1,9}\s+\d{2,3}[A-Z]?)*)\s*\.")
CODE_IN_TEXT = re.compile(r"[A-Z][A-Z&]{1,9}\s+\d{2,3}[A-Z]?")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class CourseExplorerClient:
    def __init__(self, cache_dir, timeout=20, retries=2, cache_ttl=21600, historical_cache_ttl=2592000, pace=0.4):
        require(math.isfinite(timeout) and 0 < timeout <= 120, "Timeout must be > 0 and <= 120 seconds")
        require(0 <= retries <= 5, "Retries must be between 0 and 5")
        require(math.isfinite(cache_ttl) and 0 <= cache_ttl <= 604800, "Cache TTL must be between 0 and 604800 seconds")
        require(math.isfinite(historical_cache_ttl) and 0 <= historical_cache_ttl <= 31536000, "Historical cache TTL must be between 0 and 31536000 seconds")
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.retries = retries
        self.cache_ttl = cache_ttl
        self.historical_cache_ttl = historical_cache_ttl
        self.cache_hits = 0
        self.network_requests = 0
        self.pace = pace
        self.last_request = 0
        self.minimum_fetch_times = {}

    @classmethod
    def from_args(cls, args):
        return cls(args.cache_dir, args.timeout, args.retries,
                   0 if args.refresh else args.cache_ttl, args.historical_cache_ttl)

    def fetch(self, url, expected_root="course", historical=False):
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        ttl = (self.historical_cache_ttl if historical else self.cache_ttl) if self.cache_ttl else 0
        if ttl and path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                age = (datetime.now(timezone.utc) - timestamp(cached["fetched_at"])).total_seconds()
                floor = self.minimum_fetch_times.get(url)
                if cached["url"] == url and 0 <= age < ttl and (floor is None or timestamp(cached["fetched_at"]) >= timestamp(floor)):
                    parse_xml(cached["body"], expected_root)
                    self.cache_hits += 1
                    return cached
            except (ValueError, KeyError, TypeError, OSError):
                pass  # Corrupt cache is replaceable; expired data is never a fallback.
        for attempt in range(self.retries + 1):
            retry_delay = min(2 ** attempt, 8)
            try:
                request = Request(url, headers={"User-Agent": "ProfessorGuide/0.1 (+https://github.com/Illini-Media-Company/professor-guide)", "Accept": "application/xml"})
                delay = self.pace - (time.monotonic() - self.last_request)
                if delay > 0:
                    time.sleep(delay)
                self.last_request = time.monotonic()
                self.network_requests += 1
                try:
                    import certifi
                    context = ssl.create_default_context(cafile=certifi.where())
                except ImportError:
                    context = ssl.create_default_context()
                with urlopen(request, timeout=self.timeout, context=context) as response:
                    body = response.read().decode("utf-8")
                parse_xml(body, expected_root)
                result = {"url": url, "fetched_at": utc_now(), "body": body}
                atomic_write_json(path, result)
                return result
            except HTTPError as error:
                if error.code in (401, 403):
                    raise AccessDenied(f"Access denied for {url}: HTTP {error.code}; collection stopped") from error
                if error.code not in (408, 429, 500, 502, 503, 504) or attempt == self.retries:
                    raise RequestError(f"Request failed for {url}: HTTP {error.code}") from error
                retry_after = error.headers.get("Retry-After") if error.headers else None
                if retry_after:
                    try:
                        seconds = float(retry_after)
                    except ValueError:
                        try:
                            seconds = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                        except (ValueError, TypeError):
                            seconds = retry_delay
                    if not math.isfinite(seconds) or seconds > 60:
                        raise RequestError(f"Server requested delayed retry for {url}; defer this refresh") from error
                    retry_delay = max(retry_delay, seconds)
            except UnicodeError as error:
                raise DataError(f"Invalid UTF-8 response for {url}") from error
            except (URLError, TimeoutError, OSError, HTTPException) as error:
                if attempt == self.retries:
                    raise RequestError(f"Request failed for {url}: {error}") from error
            time.sleep(retry_delay)
        raise RequestError(f"Request failed for {url}")


def optional_text(element, path):
    child = element.find(path)
    return None if child is None else "".join(child.itertext()).strip()


def check_parents(root, year, season, subject, number=None):
    calendar = root.find("parents/calendarYear")
    require(calendar is not None and calendar.get("id") == str(year), "XML year missing or mismatched")
    term = root.find("parents/term")
    require(term is not None and term.get("href") == f"{API_BASE}/{year}/{season}.xml", "XML term mismatch")
    source_subject = root.find("parents/subject")
    require(source_subject is not None and source_subject.get("id") == subject, "XML subject missing or mismatched")
    if number is not None:
        course = root.find("parents/course")
        require(course is not None and course.get("id") == number, "XML course missing or mismatched")
    return {"id": f"{year}-{season}", "year": year, "season": season, "source_term_id": term.get("id"), "label": term.text}


def parse_section(element, course_code, term, fetched_at):
    subject, number = course_code.split()
    check_parents(element, term["year"], term["season"], subject, number)
    crn = element.get("id")
    section_id = f'{term["id"]}:{crn}'
    meetings = []
    for index, meeting in enumerate(element.findall("meetings/meeting")):
        container = meeting.find("instructors")
        instructors = []
        for instructor in meeting.findall("instructors/instructor"):
            instructors.append({
                "name_raw": "".join(instructor.itertext()).strip(),
                "first_name_raw": instructor.get("firstName"),
                "last_name_raw": instructor.get("lastName"),
                "professor_id": None,
                "match_status": "unresolved",
            })
        meeting_type = meeting.find("type")
        require(meeting_type is not None, f"Missing meeting type in {section_id}")
        meetings.append({
            "id": f"{section_id}:{index}",
            "source_meeting_id": meeting.get("id"),
            "type": {"code": meeting_type.get("code"), "label": optional_text(meeting, "type")},
            "start": optional_text(meeting, "start"),
            "end": optional_text(meeting, "end"),
            "days_of_week": optional_text(meeting, "daysOfTheWeek"),
            "room": optional_text(meeting, "roomNumber"),
            "building": optional_text(meeting, "buildingName"),
            "instructor_list_status": "listed" if instructors else ("empty" if container is not None else "missing"),
            "instructors": instructors,
        })
    return {
        "id": section_id, "term_id": term["id"], "crn": crn,
        "course_code": course_code, "listing_id": f'{term["id"]}:{course_code}',
        "section_label": optional_text(element, "sectionNumber"),
        "source_url": element.get("href"), "collected_at": fetched_at,
        "section_text": optional_text(element, "sectionText"),
        "section_notes": optional_text(element, "sectionNotes"),
        "status_code": optional_text(element, "statusCode"),
        "part_of_term": optional_text(element, "partOfTerm"),
        "start_date": optional_text(element, "startDate"),
        "end_date": optional_text(element, "endDate"),
        "meetings": meetings,
    }


def extract_relationships(courses):
    """Only explicit, punctuated directives; never infer from schedule similarity."""
    collected = {}
    listings = {course["course_code"]: course["listing_id"] for course in courses}
    for course in courses:
        for field in ("description", "course_section_information"):
            for match in DIRECTIVE.finditer(course[field] or ""):
                prefix = course[field][:match.start()].rstrip()
                if prefix and prefix[-1] not in ".!?":
                    continue  # A reference embedded in prerequisite prose is not an alias.
                relation = "same_as" if match[1] == "Same as" else "see"
                for target in CODE_IN_TEXT.findall(match[2]):
                    target = " ".join(target.split())
                    if target == course["course_code"]:
                        continue
                    key = (course["listing_id"], target, relation)
                    if key not in collected:
                        collected[key] = {"from_listing_id": course["listing_id"], "to_course_code": target, "to_listing_id": listings.get(target), "relation": relation, "evidence": []}
                    collected[key]["evidence"].append({"text": match[0], "source_field": field, "source_url": course["source_url"]})
    return list(collected.values())


def build_snapshot(client, year, season, course_codes, data_kind="live"):
    courses, sections, sources = [], [], []
    term = None
    for code in course_codes:
        subject, number = code.split()
        url = f"{API_BASE}/{year}/{season}/{subject}/{number}.xml"
        index_response = client.fetch(url, historical=historical_year(year))
        detail_response = client.fetch(url + "?mode=detail", historical=historical_year(year))
        index_root = parse_xml(index_response["body"])
        detail_root = parse_xml(detail_response["body"])
        expected_term = check_parents(index_root, year, season, subject)
        require(check_parents(detail_root, year, season, subject) == expected_term, "Index/detail term mismatch")
        if term is None:
            term = expected_term
        require(term == expected_term, "Courses disagree about term")
        require(index_root.get("id") == detail_root.get("id") == code, "XML course ID mismatch")
        require(optional_text(index_root, "label") == optional_text(detail_root, "label"), "Index/detail title mismatch")
        index_sections = index_root.findall("sections/section")
        detail_sections = detail_root.findall("detailedSections/detailedSection")
        expected_crns = [section.get("id") for section in index_sections]
        actual_crns = [section.get("id") for section in detail_sections]
        require(expected_crns and len(set(expected_crns)) == len(expected_crns), f"Missing/duplicate CRNs for {code}")
        require(len(actual_crns) == len(expected_crns) and set(actual_crns) == set(expected_crns), f"Incomplete detailed sections for {code}; recollect with --refresh")
        parsed_sections = [parse_section(section, code, term, detail_response["fetched_at"]) for section in detail_sections]
        labels = {section.get("id"): section.text for section in index_sections}
        require(all(section["section_label"] == labels[section["crn"]] for section in parsed_sections), "Index/detail section label mismatch")
        courses.append({
            "course_code": code, "listing_id": f'{term["id"]}:{code}', "term_id": term["id"],
            "title": optional_text(index_root, "label"),
            "description": optional_text(index_root, "description"),
            "course_section_information": optional_text(index_root, "courseSectionInformation"),
            "credit_hours": optional_text(index_root, "creditHours"),
            "source_url": url, "detail_source_url": url + "?mode=detail",
            "collected_at": max(index_response["fetched_at"], detail_response["fetched_at"], key=timestamp),
            "section_ids": [section["id"] for section in parsed_sections],
        })
        sections.extend(parsed_sections)
        sources.extend({"url": response["url"], "fetched_at": response["fetched_at"]} for response in (index_response, detail_response))
    snapshot = {
        "schema_version": 1, "dataset": "course_explorer", "data_kind": data_kind,
        "collected_at": max((source["fetched_at"] for source in sources), key=timestamp),
        "term": term, "requested_courses": course_codes, "sources": sources,
        "courses": courses, "sections": sections, "relationships": extract_relationships(courses),
    }
    return validate_snapshot(snapshot)


def collect_to_file(client, year, season, course_codes, output):
    output = Path(output)
    require(not output.resolve().is_relative_to((ROOT / "public").resolve()), "Collect outside public/; publish with scripts.publish_data")
    discovery = CourseExplorerDiscovery(client)
    term, evidence = discovery.term(year, season)
    require(term is not None, f"Unavailable term {year}-{season}: {evidence['reason']}")
    for code in course_codes:
        available, evidence = discovery.course(term, code)
        require(available, f"Unavailable course {code} in {term['id']}: {evidence['reason']}")
    snapshot = build_snapshot(client, year, season, course_codes)
    require(snapshot["term"] == term, "Collected term disagrees with discovery index")
    atomic_write_json(output, snapshot)
    return snapshot


def normalize_course(value):
    match = re.fullmatch(r"([A-Za-z][A-Za-z&]{1,9})[ :]*(\d{2,3}[A-Za-z]?)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError('Use a course code such as "CS 374" or ECE374')
    result = f"{match[1].upper()} {match[2].upper()}"
    require(bool(COURSE_PATTERN.fullmatch(result)), "Invalid course code")
    return result


def add_client_arguments(parser):
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/course-explorer")
    parser.add_argument("--cache-ttl", type=float, default=21600, help="Current-year/discovery cache seconds (default 6 hours)")
    parser.add_argument("--historical-cache-ttl", type=float, default=2592000, help="Prior-year cache seconds (default 30 days)")
    parser.add_argument("--timeout", type=float, default=20, help="Per request timeout in seconds")
    parser.add_argument("--retries", type=int, default=2, help="Retries after the initial request (0–5)")
    parser.add_argument("--refresh", action="store_true", help="Bypass all caches; never fall back to stale responses")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--term", choices=TERMS, default="fall")
    parser.add_argument("--courses", nargs="+", type=normalize_course, default=["CS 374", "ECE 374"])
    parser.add_argument("--output", type=Path, help="Default: data/snapshots/course-explorer-YEAR-TERM.json")
    add_client_arguments(parser)
    args = parser.parse_args()
    output = args.output or ROOT / f"data/snapshots/course-explorer-{args.year}-{args.term}.json"
    try:
        require(1900 <= args.year <= 2200, "Invalid year")
        require(len(args.courses) == len(set(args.courses)), "Duplicate requested courses")
        client = CourseExplorerClient.from_args(args)
        snapshot = collect_to_file(client, args.year, args.term, args.courses, output)
    except (DataError, OSError, AttributeError) as error:
        print(f"Collection failed; existing snapshot preserved: {error}", file=sys.stderr)
        return 1
    print(f'Collected {len(snapshot["courses"])} listings / {len(snapshot["sections"])} sections → {output}')
    print(f'Source collection timestamp: {snapshot["collected_at"]}. Publication is a separate command.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
