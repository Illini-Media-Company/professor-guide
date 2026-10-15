"""Collect discovered departments using verified cascade endpoints; fail closed."""

import argparse
from copy import deepcopy
from pathlib import Path
import sys

from scripts.collect_course_explorer import (
    CourseExplorerClient, add_client_arguments, check_parents, extract_relationships,
    optional_text, parse_section,
)
from scripts.course_explorer_discovery import CourseExplorerDiscovery, historical_year
from scripts.data_contract import API_BASE, AccessDenied, DataError, atomic_write_json, require, timestamp, validate_snapshot
from scripts.teaching_history import counts, parse_term_id


def subjects_for(discovery, term):
    url = f'{API_BASE}/{term["year"]}/{term["season"]}.xml'
    root, _ = discovery.read(url, "term", historical_year(term["year"]))
    require(root.get("id") == term["source_term_id"], "Term ID mismatch")
    return [entry.get("id") for entry in discovery.entries(root, "subjects", "subject")]


def department_snapshot(discovery, term, subject):
    base = f'{API_BASE}/{term["year"]}/{term["season"]}/{subject}'
    index, index_time = discovery.read(base + ".xml", "subject", historical_year(term["year"]))
    detail, detail_time = discovery.read(base + ".xml?mode=cascade", "subject", historical_year(term["year"]))
    require(index.get("id") == detail.get("id") == subject, "Department ID mismatch")
    expected = discovery.entries(index, "courses", "course")
    container = detail.find("cascadingCourses")
    require(container is not None, "Missing cascadingCourses")
    children = list(container)
    require(all(child.tag == "cascadingCourse" for child in children), "Unexpected cascading course")
    expected_codes = [f'{subject} {entry.get("id")}' for entry in expected]
    actual_codes = [entry.get("id") for entry in children]
    require(len(set(actual_codes)) == len(actual_codes) and set(actual_codes) == set(expected_codes), "Department index/cascade course mismatch")
    if not expected_codes:
        return None
    courses, sections = [], []
    labels = {f'{subject} {entry.get("id")}': (entry.text or "").strip() for entry in expected}
    for element in children:
        code = element.get("id")
        require(check_parents(element, term["year"], term["season"], subject) == term, "Batch course term mismatch")
        number = code.split()[1]
        require(optional_text(element, "label") == labels[code], f"Department index/cascade label mismatch for {code}")
        section_container = element.find("detailedSections")
        require(section_container is not None, f"Missing detailedSections for {code}")
        parsed = []
        for child in section_container:
            require(child.tag == "detailedSection", "Unexpected section element")
            record = parse_section(child, code, term, detail_time)
            record["response_source_url"] = base + ".xml?mode=cascade"
            if not record["section_label"]:
                record["section_label_status"] = "missing" if child.find("sectionNumber") is None else "empty"
            if not record["meetings"]:
                record["meeting_status"] = "missing" if child.find("meetings") is None else "empty"
            parsed.append(record)
        canonical = base + f"/{number}.xml"
        courses.append({
            "course_code": code, "listing_id": f'{term["id"]}:{code}', "term_id": term["id"],
            "title": optional_text(element, "label"), "description": optional_text(element, "description"),
            "course_section_information": optional_text(element, "courseSectionInformation"),
            "credit_hours": optional_text(element, "creditHours"), "source_url": canonical,
            "detail_source_url": canonical + "?mode=detail", "index_response_url": base + ".xml",
            "detail_response_url": base + ".xml?mode=cascade",
            "collected_at": max(index_time, detail_time, key=timestamp),
            "section_ids": [record["id"] for record in parsed],
            "schedule_status": "listed" if parsed else "no_sections",
        })
        sections.extend(parsed)
    return validate_snapshot({
        "schema_version": 1, "dataset": "course_explorer", "data_kind": "live", "term": term,
        "collected_at": max(index_time, detail_time, key=timestamp), "requested_courses": expected_codes,
        "courses": courses, "sections": sections, "relationships": extract_relationships(courses),
        "sources": [{"url": base + ".xml", "fetched_at": index_time}, {"url": base + ".xml?mode=cascade", "fetched_at": detail_time}],
    })


def merge_departments(parts):
    require(parts, "No department schedules collected")
    result = deepcopy(parts[0])
    for field in ("courses", "sections", "sources", "requested_courses"):
        result[field] = [value for part in parts for value in part[field]]
    result["collected_at"] = max((part["collected_at"] for part in parts), key=timestamp)
    result["relationships"] = extract_relationships(result["courses"])
    return validate_snapshot(result)


def collect(client, term_id, output, subjects=None, courses=None):
    discovery = CourseExplorerDiscovery(client)
    term, evidence = discovery.term(*parse_term_id(term_id))
    require(term is not None, f"Unavailable term: {evidence}")
    available = subjects_for(discovery, term)
    wanted = subjects or (sorted({code.split()[0] for code in courses}) if courses else available)
    require(set(wanted) <= set(available), f"Unavailable departments: {set(wanted) - set(available)}")
    parts, rows = [], []
    report_path = Path(output).with_suffix(".coverage.json")
    for index, subject in enumerate(wanted, 1):
        try:
            part = department_snapshot(discovery, term, subject)
            if part and courses:
                selected = [course for course in part["courses"] if course["course_code"] in courses]
                part["courses"] = selected
                part["requested_courses"] = [course["course_code"] for course in selected]
                part["sections"] = [section for section in part["sections"] if section["course_code"] in part["requested_courses"]]
                part["relationships"] = extract_relationships(selected)
                if selected:
                    validate_snapshot(part)
                else:
                    part = None
            if part:
                parts.append(part)
            row = {"subject": subject, "status": "collected" if part else "no_listings", "course_count": len(part["courses"]) if part else 0, **counts(part["sections"] if part else [])}
        except AccessDenied as error:
            rows.append({"subject": subject, "status": "access_denied", "error": str(error)})
            atomic_write_json(report_path, {"term_id": term_id, "discovered_subjects": available, "requested_subjects": wanted, "departments": rows})
            raise
        except (DataError, OSError) as error:
            rows.append({"subject": subject, "status": "error", "error": str(error)})
            atomic_write_json(report_path, {"term_id": term_id, "discovered_subjects": available, "requested_subjects": wanted, "departments": rows})
            raise DataError(f'{subject} collection failed; previous snapshot preserved: {error}') from error
        rows.append(row)
        atomic_write_json(report_path, {"term_id": term_id, "discovered_subjects": available, "requested_subjects": wanted, "departments": rows})
        print(f'[{index}/{len(wanted)}] {subject}: {row["status"]} {row.get("course_count", "")} {row.get("error", "")}', flush=True)
    snapshot = merge_departments(parts)
    if courses:
        require(set(courses) == set(snapshot["requested_courses"]), "Some requested courses are unavailable; see department indexes")
    atomic_write_json(output, snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", required=True)
    parser.add_argument("--subjects", nargs="+")
    parser.add_argument("--courses", nargs="+")
    parser.add_argument("--output", type=Path, default=Path("data/snapshots/campus-schedule.json"))
    add_client_arguments(parser)
    args = parser.parse_args()
    try:
        require(not args.output.resolve().is_relative_to(Path("public").resolve()), "Collect outside public/")
        collect(CourseExplorerClient.from_args(args), args.term, args.output, args.subjects, args.courses)
    except (DataError, OSError) as error:
        print(f"Collection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
