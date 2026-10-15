"""Shared snapshot validation and atomic JSON writes; no third-party dependencies."""

import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime

API_BASE = "https://courses.illinois.edu/cisapp/explorer/schedule"
COURSE_PATTERN = re.compile(r"[A-Z][A-Z&]{1,9} \d{2,3}[A-Z]?")
TERMS = ("spring", "summer", "fall", "winter")


class DataError(ValueError):
    """An upstream response or candidate snapshot cannot safely be used."""


class RequestError(DataError):
    """An HTTP/transport failure; it does not prove that a listing is unavailable."""


class AccessDenied(RequestError):
    """An explicit access restriction. Do not retry or continue collection."""


def require(condition, message):
    if not condition:
        raise DataError(message)


def timestamp(value):
    require(isinstance(value, str), "Timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DataError(f"Invalid timestamp: {value}") from error
    require(parsed.tzinfo is not None, "Timestamp must include a timezone")
    return parsed


def text_field(record, key):
    require(isinstance(record.get(key), str) and bool(record[key].strip()), f"Missing {key}")


def validate_snapshot(data):
    """Reject incomplete or inconsistent snapshots before any destination is replaced."""
    try:
        require(data["schema_version"] == 1, "Unsupported schema_version")
        require(data["dataset"] == "course_explorer", "Unexpected dataset")
        require(data["data_kind"] in ("live", "development_fixture"), "Unknown data_kind")
        timestamp(data["collected_at"])
        term = data["term"]
        require(type(term["year"]) is int and 1900 <= term["year"] <= 2200, "Invalid year")
        require(term["season"] in TERMS, "Invalid term")
        term_id = f'{term["year"]}-{term["season"]}'
        require(term["id"] == term_id, "Term ID mismatch")
        text_field(term, "source_term_id")
        text_field(term, "label")
        base = f'{API_BASE}/{term["year"]}/{term["season"]}'
        require(isinstance(data["requested_courses"], list) and data["requested_courses"], "No requested courses")
        require(len(set(data["requested_courses"])) == len(data["requested_courses"]), "Duplicate request")
        require(isinstance(data["courses"], list) and data["courses"], "No courses")
        courses = {}
        listing_ids = set()
        referenced_sections = set()
        for course in data["courses"]:
            code = course["course_code"]
            require(bool(COURSE_PATTERN.fullmatch(code)), f"Invalid course code: {code}")
            require(code not in courses, "Duplicate course")
            courses[code] = course
            require(course["listing_id"] == f"{term_id}:{code}", "Listing ID mismatch")
            require(course["term_id"] == term_id, "Course term mismatch")
            listing_ids.add(course["listing_id"])
            text_field(course, "title")
            subject, number = code.split()
            url = f"{base}/{subject}/{number}.xml"
            require(course["source_url"] == url, "Course URL mismatch")
            require(course["detail_source_url"] == url + "?mode=detail", "Detail URL mismatch")
            if "detail_response_url" in course or "index_response_url" in course:
                subject_url = f"{base}/{subject}.xml"
                require(course.get("index_response_url") == subject_url and course.get("detail_response_url") == subject_url + "?mode=cascade", "Batch response URL mismatch")
            timestamp(course["collected_at"])
            require(isinstance(course["section_ids"], list) and (course["section_ids"] or course.get("schedule_status") == "no_sections"), f"No sections for {code}")
            require(len(set(course["section_ids"])) == len(course["section_ids"]), "Duplicate section reference")
            referenced_sections.update(course["section_ids"])
        require(set(courses) == set(data["requested_courses"]), "Missing or unexpected requested course")
        require(isinstance(data["sections"], list), "Invalid sections")
        section_ids = set()
        for section in data["sections"]:
            code = section["course_code"]
            require(code in courses, "Section references an unknown course")
            require(section["term_id"] == term_id, "Section term mismatch")
            require(section["listing_id"] == courses[code]["listing_id"], "Section listing mismatch")
            require(isinstance(section["crn"], str) and bool(re.fullmatch(r"\d{5}", section["crn"])), "Invalid CRN")
            section_id = f'{term_id}:{section["crn"]}'
            require(section["id"] == section_id, "Section ID must be term + CRN")
            require(section_id not in section_ids, "Duplicate section ID")
            section_ids.add(section_id)
            require(section_id in courses[code]["section_ids"], "Section missing from its course")
            require(section["source_url"] == courses[code]["source_url"].removesuffix(".xml") + f'/{section["crn"]}.xml', "Section URL mismatch")
            timestamp(section["collected_at"])
            if section.get("section_label_status") not in ("missing", "empty"):
                text_field(section, "section_label")
            require(isinstance(section["meetings"], list) and (section["meetings"] or section.get("meeting_status") in ("empty", "missing")), "No meetings: upstream shape may have changed")
            meeting_ids = set()
            for meeting in section["meetings"]:
                require(meeting["id"].startswith(section_id + ":"), "Meeting ID mismatch")
                require(meeting["id"] not in meeting_ids, "Duplicate meeting ID")
                meeting_ids.add(meeting["id"])
                text_field(meeting["type"], "code")
                text_field(meeting["type"], "label")
                require(meeting["instructor_list_status"] in ("listed", "empty", "missing"), "Invalid instructor status")
                require(isinstance(meeting["instructors"], list), "Instructors must be a list")
                require(bool(meeting["instructors"]) == (meeting["instructor_list_status"] == "listed"), "Instructor status mismatch")
                for instructor in meeting["instructors"]:
                    text_field(instructor, "name_raw")
                    require(instructor["professor_id"] is None and instructor["match_status"] == "unresolved", "Collector snapshots must keep matches unresolved")
        require(referenced_sections == section_ids, "Dangling section references")
        require(isinstance(data["sources"], list) and data["sources"], "Missing source provenance")
        sources = {}
        for source in data["sources"]:
            require(source["url"] not in sources, "Duplicate source URL")
            sources[source["url"]] = source["fetched_at"]
            timestamp(source["fetched_at"])
        for course in courses.values():
            expected_urls = (course.get("index_response_url", course["source_url"]), course.get("detail_response_url", course["detail_source_url"]))
            require(all(url in sources for url in expected_urls), "Missing course source")
            require(course["collected_at"] == max((sources[url] for url in expected_urls), key=timestamp), "Course timestamp mismatch")
        require(data["collected_at"] == max(sources.values(), key=timestamp), "Snapshot timestamp mismatch")
        for section in data["sections"]:
            course = courses[section["course_code"]]
            require(section["collected_at"] == sources[course.get("detail_response_url", course["detail_source_url"])] , "Section timestamp mismatch")
            if "response_source_url" in section:
                require(section["response_source_url"] == course.get("detail_response_url", course["detail_source_url"]), "Section response URL mismatch")
        require(isinstance(data["relationships"], list), "Relationships must be a list")
        for relationship in data["relationships"]:
            require(relationship["from_listing_id"] in listing_ids, "Unknown relationship origin")
            require(bool(COURSE_PATTERN.fullmatch(relationship["to_course_code"])), "Invalid related course")
            require(relationship["relation"] in ("same_as", "see"), "Unsupported relationship")
            target = f'{term_id}:{relationship["to_course_code"]}'
            require(relationship["to_listing_id"] == (target if target in listing_ids else None), "Relationship target mismatch")
            require(relationship["evidence"], "Relationships require explicit source evidence")
            for evidence in relationship["evidence"]:
                text_field(evidence, "text")
                require(evidence["source_field"] in ("description", "course_section_information"), "Invalid evidence field")
                origin = next(c for c in courses.values() if c["listing_id"] == relationship["from_listing_id"])
                require(evidence["source_url"] == origin["source_url"], "Invalid evidence URL")
                require(evidence["text"] in origin[evidence["source_field"]], "Evidence does not appear in source text")
    except (KeyError, TypeError, AttributeError) as error:
        raise DataError(f"Malformed snapshot: {error}") from error
    return data


def atomic_write_json(path, data):
    """Serialize fully, then replace one file on the same filesystem."""
    body = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    atomic_write_text(path, body)


def atomic_write_text(path, body):
    """Write one complete report or serialized snapshot before replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(body)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_document(data):
    if isinstance(data, dict) and data.get("dataset") == "teaching_history":
        from scripts.teaching_history import validate_history
        return validate_history(data)
    return validate_snapshot(data)
