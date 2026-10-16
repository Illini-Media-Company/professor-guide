"""Course Explorer HTTP client, XML section parsing, and explicit alias extraction."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from http.client import HTTPException
import json
import math
import ssl
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.data_contract import AccessDenied, DataError, RequestError, atomic_write_json, require, timestamp
from scripts.course_explorer_discovery import parse_xml

ROOT = Path(__file__).resolve().parents[1]
DIRECTIVE = re.compile(r"\b(Same as|See)\s+([A-Z][A-Z&]{1,9}\s+\d{2,3}[A-Z]?(?:\s*(?:,|and|/)\s*[A-Z][A-Z&]{1,9}\s+\d{2,3}[A-Z]?)*)\s*\.")
CODE_IN_TEXT = re.compile(r"[A-Z][A-Z&]{1,9}\s+\d{2,3}[A-Z]?")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class CourseExplorerClient:
    def __init__(self, cache_dir, timeout=20, retries=2, cache_ttl=21600, historical_cache_ttl=2592000, pace=1.0):
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
                    if response.status == 202 or response.headers.get('x-amzn-waf-action') in ('challenge', 'captcha'):
                        raise AccessDenied(f'Automated-access challenge for {url}; collection stopped without retry')
                    require(response.status == 200, f'Unexpected HTTP status for {url}: {response.status}')
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


def add_client_arguments(parser):
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/course-explorer")
    parser.add_argument("--cache-ttl", type=float, default=21600, help="Current-year/discovery cache seconds (default 6 hours)")
    parser.add_argument("--historical-cache-ttl", type=float, default=2592000, help="Prior-year cache seconds (default 30 days)")
    parser.add_argument("--timeout", type=float, default=20, help="Per request timeout in seconds")
    parser.add_argument("--retries", type=int, default=2, help="Retries after the initial request (0–5)")
    parser.add_argument("--refresh", action="store_true", help="Bypass all caches; never fall back to stale responses")

