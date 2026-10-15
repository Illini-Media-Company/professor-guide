"""Collect discovered departments using verified cascade endpoints; fail closed."""

import argparse
import json
from pathlib import Path
import sys

from scripts.campus import department_snapshot, merge_departments, subjects_for
from scripts.collect_course_explorer import CourseExplorerClient, add_client_arguments
from scripts.course_explorer_discovery import CourseExplorerDiscovery
from scripts.data_contract import AccessDenied, DataError, atomic_write_json, require, validate_snapshot
from scripts.teaching_history import counts, parse_term_id


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
                from scripts.collect_course_explorer import extract_relationships
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
            row = {"subject": subject, "status": "error", "error": str(error)}
        rows.append(row)
        atomic_write_json(report_path, {"term_id": term_id, "discovered_subjects": available, "requested_subjects": wanted, "departments": rows})
        print(f'[{index}/{len(wanted)}] {subject}: {row["status"]} {row.get("course_count", "")} {row.get("error", "")}', flush=True)
    errors = [row for row in rows if row["status"] == "error"]
    require(not errors, f"{len(errors)} departments failed; previous snapshot preserved; see {report_path}")
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
