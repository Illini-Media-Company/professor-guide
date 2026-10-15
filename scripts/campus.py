"""Department batch collection with unchanged registration identifiers."""

from copy import deepcopy
import xml.etree.ElementTree as ET

from scripts.collect_course_explorer import check_parents, optional_text, parse_section, extract_relationships
from scripts.course_explorer_discovery import historical_year, parse_xml
from scripts.data_contract import API_BASE, DataError, require, timestamp, validate_snapshot


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
