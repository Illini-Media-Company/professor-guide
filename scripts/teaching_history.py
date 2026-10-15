"""Multi-term collection, bundle validation, and readable teaching-history coverage."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from scripts.collect_course_explorer import build_snapshot, extract_relationships
from scripts.course_explorer_discovery import CourseExplorerDiscovery
from scripts.data_contract import (
    API_BASE, COURSE_PATTERN, TERMS, AccessDenied, DataError, RequestError,
    atomic_write_text, require, timestamp, validate_snapshot,
)

COUNT_FIELDS = (
    "section_count", "meeting_count", "missing_instructor_meetings",
    "multiple_instructor_meetings", "instructor_occurrences", "unresolved_occurrences",
)


def parse_term_id(value):
    match = re.fullmatch(r"(\d{4})-([a-z]+)", value)
    require(match is not None and match[2] in TERMS, "Use a term ID such as 2026-fall")
    year = int(match[1])
    require(1900 <= year <= 2200, "Invalid year")
    return year, match[2]


def counts(sections):
    meetings = [meeting for section in sections for meeting in section["meetings"]]
    instructors = [instructor for meeting in meetings for instructor in meeting["instructors"]]
    return {
        "section_count": len(sections), "meeting_count": len(meetings),
        "missing_instructor_meetings": sum(not meeting["instructors"] for meeting in meetings),
        "multiple_instructor_meetings": sum(len(meeting["instructors"]) > 1 for meeting in meetings),
        "instructor_occurrences": len(instructors),
        "unresolved_occurrences": sum(instructor["professor_id"] is None for instructor in instructors),
        "meeting_types": dict(sorted(Counter(meeting["type"]["code"] for meeting in meetings).items())),
    }


def coverage_totals(term_rows, course_rows, snapshots):
    totals = {
        "requested_terms": len(term_rows),
        "available_terms": sum(row["status"] == "available" for row in term_rows),
        "collected_terms": len(snapshots),
        "requested_course_terms": len(course_rows),
        "collected_course_terms": sum(row["status"] == "collected" for row in course_rows),
        "unavailable_course_terms": sum(row["status"] == "unavailable" for row in course_rows),
        "error_course_terms": sum(row["status"] == "error" for row in course_rows),
    }
    totals.update(counts([section for snapshot in snapshots for section in snapshot["sections"]]))
    return totals


def merge_snapshots(parts):
    first = parts[0]
    courses = [course for part in parts for course in part["courses"]]
    return validate_snapshot({
        "schema_version": 1, "dataset": "course_explorer", "data_kind": first["data_kind"],
        "collected_at": max((part["collected_at"] for part in parts), key=timestamp),
        "term": first["term"], "requested_courses": [course["course_code"] for course in courses],
        "sources": [source for part in parts for source in part["sources"]],
        "courses": courses, "sections": [section for part in parts for section in part["sections"]],
        "relationships": extract_relationships(courses),
    })


def error_fields(error):
    return {"status": "error", "reason": str(error), "error_kind": "request" if isinstance(error, RequestError) else "validation"}


def build_history(client, term_ids, course_codes, data_kind="live"):
    require(term_ids and len(set(term_ids)) == len(term_ids), "Missing/duplicate requested terms")
    require(course_codes and len(set(course_codes)) == len(course_codes), "Missing/duplicate requested courses")
    require(all(COURSE_PATTERN.fullmatch(code) for code in course_codes), "Invalid requested course")
    for term_id in term_ids:
        parse_term_id(term_id)
    discovery = CourseExplorerDiscovery(client)
    term_rows, course_rows, snapshots = [], [], []
    for term_id in term_ids:
        year, season = parse_term_id(term_id)
        try:
            term, evidence = discovery.term(year, season)
            term_row = {"term_id": term_id, "status": "available" if term else "unavailable", **evidence}
            if term:
                term_row["term"] = term
        except AccessDenied:
            raise
        except DataError as error:
            term, term_row = None, {"term_id": term_id, **error_fields(error)}
        term_rows.append(term_row)
        parts = []
        for code in course_codes:
            row = {"term_id": term_id, "course_code": code, **counts([])}
            if term is None:
                row.update({key: value for key, value in term_row.items() if key != "term_id"})
            else:
                try:
                    available, evidence = discovery.course(term, code)
                    row.update({"status": "unavailable", **evidence})
                    if available:
                        part = build_snapshot(client, year, season, [code], data_kind)
                        require(part["term"] == term, "Collected term disagrees with discovery index")
                        parts.append(part)
                        row.update({"status": "collected", **counts(part["sections"])})
                except AccessDenied:
                    raise
                except DataError as error:
                    row.update(error_fields(error))
            course_rows.append(row)
        if parts:
            try:
                snapshots.append(merge_snapshots(parts))
            except DataError as error:
                for row in course_rows:
                    if row["term_id"] == term_id and row["status"] == "collected":
                        row.update({**counts([]), **error_fields(error)})
    discovery_sources = list(discovery.sources.values())
    times = [source["fetched_at"] for source in discovery_sources] + [snapshot["collected_at"] for snapshot in snapshots]
    document = {
        "schema_version": 1, "dataset": "teaching_history", "data_kind": data_kind,
        "collected_at": max(times, key=timestamp) if times else None,
        "requested_terms": term_ids, "requested_courses": course_codes,
        "discovery_sources": discovery_sources, "snapshots": snapshots,
        "coverage": {"terms": term_rows, "courses": course_rows, "totals": coverage_totals(term_rows, course_rows, snapshots)},
    }
    # A failed attempt is reportable, but never a valid publishable snapshot.
    if not any(row["status"] == "error" for row in term_rows + course_rows):
        validate_history(document)
    return document


def validate_history(data):
    """Validate the additive bundle, including exact coverage and original v1 snapshots."""
    try:
        require(data["schema_version"] == 1 and data["dataset"] == "teaching_history", "Unsupported history format")
        require(data["data_kind"] in ("live", "development_fixture"), "Unknown data_kind")
        term_ids, codes = data["requested_terms"], data["requested_courses"]
        require(isinstance(term_ids, list) and term_ids and len(set(term_ids)) == len(term_ids), "Missing/duplicate requested terms")
        require(isinstance(codes, list) and codes and len(set(codes)) == len(codes), "Missing/duplicate requested courses")
        for term_id in term_ids:
            parse_term_id(term_id)
        require(all(COURSE_PATTERN.fullmatch(code) for code in codes), "Invalid course code")
        require(isinstance(data["snapshots"], list), "Snapshots must be a list")
        snapshots, listings = {}, {}
        for snapshot in data["snapshots"]:
            validate_snapshot(snapshot)
            term_id = snapshot["term"]["id"]
            require(term_id in term_ids and term_id not in snapshots, "Unexpected/duplicate snapshot term")
            require(snapshot["data_kind"] == data["data_kind"], "Mixed live/fixture data")
            snapshots[term_id] = snapshot
            for course in snapshot["courses"]:
                require(course["course_code"] in codes, "Unexpected course in history")
                listings[(term_id, course["course_code"])] = [section for section in snapshot["sections"] if section["listing_id"] == course["listing_id"]]
        sources = {}
        for source in data["discovery_sources"]:
            require(source["url"].startswith(API_BASE), "Unexpected discovery URL")
            require(source["url"] not in sources, "Duplicate discovery source")
            timestamp(source["fetched_at"])
            sources[source["url"]] = source["fetched_at"]
        require(API_BASE + ".xml" in sources, "Missing calendar year discovery source")
        times = list(sources.values()) + [snapshot["collected_at"] for snapshot in snapshots.values()]
        require(data["collected_at"] == max(times, key=timestamp), "History timestamp mismatch")
        coverage = data["coverage"]
        require(isinstance(coverage["terms"], list) and isinstance(coverage["courses"], list), "Invalid coverage rows")
        require([row["term_id"] for row in coverage["terms"]] == term_ids, "Term coverage mismatch")
        expected_pairs = [(term, code) for term in term_ids for code in codes]
        require([(row["term_id"], row["course_code"]) for row in coverage["courses"]] == expected_pairs, "Course/term coverage mismatch")
        term_rows = {row["term_id"]: row for row in coverage["terms"]}
        for row in coverage["terms"] + coverage["courses"]:
            require(row["status"] != "error", "Failed collection attempts cannot be published")
            require(row["source_url"] in sources and row["checked_at"] == sources[row["source_url"]], "Missing availability provenance")
            year, season = parse_term_id(row["term_id"])
            year_url, term_url = f"{API_BASE}/{year}.xml", f"{API_BASE}/{year}/{season}.xml"
            if "course_code" not in row:
                require(row["status"] in ("available", "unavailable"), "Unknown term availability")
                if row["status"] == "available":
                    require(row["reason"] == "term_listed" and row["source_url"] == year_url, "Invalid term discovery evidence")
                    require(row["term"]["id"] == row["term_id"], "Discovered term ID mismatch")
                    if row["term_id"] in snapshots:
                        require(row["term"] == snapshots[row["term_id"]]["term"], "Snapshot/discovery term mismatch")
                else:
                    expected_url = API_BASE + ".xml" if row["reason"] == "year_not_listed" else year_url
                    require(row["reason"] in ("year_not_listed", "term_not_listed") and row["source_url"] == expected_url, "Invalid unavailable-term evidence")
            else:
                require(row["status"] in ("collected", "unavailable"), "Unknown course availability")
                pair = row["term_id"], row["course_code"]
                require((pair in listings) == (row["status"] == "collected"), "Collected-course coverage mismatch")
                metrics = counts(listings.get(pair, []))
                require(all(row[key] == value for key, value in metrics.items()), "Coverage counts disagree with snapshots")
                subject_url = term_url.removesuffix(".xml") + f'/{row["course_code"].split()[0]}.xml'
                if row["status"] == "collected":
                    require(row["reason"] == "course_listed" and row["source_url"] == subject_url, "Invalid course discovery evidence")
                    require(term_rows[row["term_id"]]["status"] == "available", "Collected course in unavailable term")
                elif term_rows[row["term_id"]]["status"] == "unavailable":
                    term_row = term_rows[row["term_id"]]
                    require(all(row[key] == term_row[key] for key in ("source_url", "checked_at", "reason")), "Unavailable course/term evidence mismatch")
                else:
                    expected_url = term_url if row["reason"] == "subject_not_listed" else subject_url
                    require(row["reason"] in ("subject_not_listed", "course_not_listed") and row["source_url"] == expected_url, "Invalid unavailable-course evidence")
        require(coverage["totals"] == coverage_totals(coverage["terms"], coverage["courses"], data["snapshots"]), "Coverage totals mismatch")
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise DataError(f"Malformed teaching history: {error}") from error
    return data


def render_report(data):
    coverage, totals = data["coverage"], data["coverage"]["totals"]
    failed = totals["error_course_terms"] > 0
    lines = [
        "# Teaching-history coverage", "",
        "**FAILED ATTEMPT — previous candidate and published snapshots are preserved.**" if failed else "Validated teaching-history collection.",
        f'Data kind: `{data["data_kind"]}`. Latest successful source fetch: `{data["collected_at"]}`.', "",
        f'Requested {totals["requested_terms"]} terms; {totals["available_terms"]} available; {totals["collected_terms"]} contain collected listings.',
        f'Requested {totals["requested_course_terms"]} course/term pairs; {totals["collected_course_terms"]} collected, {totals["unavailable_course_terms"]} unavailable, {totals["error_course_terms"]} failed.', "",
        "| Term | Course | Status | Sections | Meetings | Missing instructors | Multiple instructors | Unresolved occurrences | Meeting roles |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in coverage["courses"]:
        roles = ", ".join(f"{code}={count}" for code, count in row["meeting_types"].items()) or "—"
        lines.append(f'| {row["term_id"]} | {row["course_code"]} | {row["status"]} | {row["section_count"]} | {row["meeting_count"]} | {row["missing_instructor_meetings"]} | {row["multiple_instructor_meetings"]} | {row["unresolved_occurrences"]} | {roles} |')
    lines.extend([
        "", f'Totals: **{totals["section_count"]} sections, {totals["meeting_count"]} meetings, {totals["instructor_occurrences"]} listed instructor occurrences**.',
        f'Missing instructor lists: {totals["missing_instructor_meetings"]} meetings. Multiple instructors: {totals["multiple_instructor_meetings"]} meetings. Unresolved: {totals["unresolved_occurrences"]} occurrences.',
        "", "Missing/multiple counts refer to meetings. Unresolved occurrences count each listed instructor on each meeting; they are not unique people. Missing lists remain empty and do not create a placeholder instructor. Cross-listed registration records remain separate, so these totals must not be interpreted as unique teaching loads or grade samples.",
        "", "## Availability evidence", "",
    ])
    for row in coverage["terms"]:
        source = f' [{row["source_url"]}]({row["source_url"]}), fetched `{row["checked_at"]}`' if "source_url" in row else ""
        lines.append(f'- `{row["term_id"]}`: {row["status"]} ({row["reason"]}).{source}')
    for row in coverage["courses"]:
        if row["status"] != "collected":
            source = f' [{row["source_url"]}]({row["source_url"]}), fetched `{row["checked_at"]}`' if "source_url" in row else ""
            lines.append(f'- `{row["term_id"]} / {row["course_code"]}`: {row["status"]} ({row.get("error_kind", "availability")}) — {row["reason"]}.{source}')
    lines.extend(["", "## Source timestamps", "", "| Term | Earliest course fetch | Latest course fetch |", "| --- | --- | --- |"])
    for snapshot in data["snapshots"]:
        times = [source["fetched_at"] for source in snapshot["sources"]]
        lines.append(f'| {snapshot["term"]["id"]} | {min(times, key=timestamp)} | {max(times, key=timestamp)} |')
    lines.extend(["", "Each course and section retains its source URL and timestamp in the snapshots. Availability checks retain their index URL and original fetch time in coverage; all discovery sources are in `discovery_sources`. Cached responses keep their original timestamps.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Render coverage from a validated saved teaching-history bundle.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = render_report(validate_history(json.loads(args.input.read_text(encoding="utf-8"))))
        if args.output:
            atomic_write_text(args.output, report)
        else:
            print(report)
    except (DataError, ValueError, OSError) as error:
        print(f"Coverage report failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
