"""Collect the same courses across discovered terms; save only a validated complete attempt."""

import argparse
from pathlib import Path
import sys

from scripts.collect_course_explorer import CourseExplorerClient, ROOT, add_client_arguments, normalize_course
from scripts.data_contract import DataError, atomic_write_json, atomic_write_text, require
from scripts.teaching_history import build_history, parse_term_id, render_report, validate_history

PILOT_TERMS = ["2026-fall", "2025-spring"]
PILOT_COURSES = ["CS 374", "ECE 374", "CS 107", "STAT 107", "IS 107"]


def collect_history_to_file(client, term_ids, course_codes, output, report_path=None, data_kind="live"):
    require(not Path(output).resolve().is_relative_to((ROOT / "public").resolve()), "Collect outside public/; publish with scripts.publish_data")
    if report_path is not None:
        require(Path(report_path).resolve() != Path(output).resolve(), "Report and candidate paths must differ")
        require(not Path(report_path).resolve().is_relative_to((ROOT / "public").resolve()), "Attempt reports must stay outside public/")
    document = build_history(client, term_ids, course_codes, data_kind)
    report = render_report(document)
    if report_path is not None:
        atomic_write_text(report_path, report)
    failures = [row for row in document["coverage"]["courses"] if row["status"] == "error"]
    require(not failures, f'{len(failures)} course/term collection errors; first: {failures[0]["reason"]}' if failures else "")
    # Validation explicitly rejects attempts containing request/parsing errors.
    validate_history(document)
    atomic_write_json(output, document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms", nargs="+", default=PILOT_TERMS, help="Term IDs such as 2026-fall 2025-spring; verified against indexes")
    parser.add_argument("--courses", nargs="+", type=normalize_course, default=PILOT_COURSES)
    parser.add_argument("--output", type=Path, default=ROOT / "data/snapshots/teaching-history.json")
    parser.add_argument("--report", type=Path, default=ROOT / "data/reports/teaching-history-latest-attempt.md")
    add_client_arguments(parser)
    args = parser.parse_args()
    try:
        for term_id in args.terms:
            parse_term_id(term_id)
        client = CourseExplorerClient.from_args(args)
        document = collect_history_to_file(client, args.terms, args.courses, args.output, args.report)
    except (DataError, OSError) as error:
        print(f"History collection failed; existing snapshots preserved: {error}", file=sys.stderr)
        print(f"Attempt report (when collection started): {args.report}", file=sys.stderr)
        return 1
    print(render_report(document))
    print(f"Candidate: {args.output}\nAttempt report: {args.report}")
    print(f"Network requests: {client.network_requests}; cache hits: {client.cache_hits}. Publication is separate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
