"""One command: discover, collect, integrate, validate, report, and publish."""

import argparse
from datetime import date
from pathlib import Path
import sys

from scripts.collect_campus import collect
from scripts.collect_course_explorer import CourseExplorerClient, add_client_arguments
from scripts.data_contract import DataError, atomic_write_text, require, timestamp
from scripts.integration import publish_bundle, read, validate_bundle, validate_input
from scripts.archive import collect_archive, render_archive_report, validate_department_coverage
from scripts.teaching_history import counts


def teammate_inputs(config):
    inputs = {}
    for name, key in (("gpa", "gpa_input"), ("professors", "professor_input"), ("verified_occurrences", "verified_links_input")):
        path = config.get(key)
        if path and Path(path).exists():
            inputs[name] = validate_input(read(path), name)
    return inputs


def history_for(config, inputs, client, public_dir, refresh=False, allow_collection=True,
                current=None, existing=None):
    if existing is None and (public_dir / "integration.json").exists():
        _, files = validate_bundle(public_dir)
        existing = files["history"]
    history = collect_archive(client, config["archive_start_year"], config["current_term"],
                              existing=existing, current=current, refresh=refresh,
                              allow_collection=allow_collection)
    for grade in inputs.get('gpa', {}).get('records', []):
        require(grade['term_id'] in history['requested_terms'],
                f'GPA term {grade["term_id"]} is outside the archive; review archive_start_year/current_term before publishing')
    return history


def report_current(manifest, coverage):
    stats = manifest["coverage"]
    lines = ["# Current campus coverage", "", f'Term: **{manifest["current_term"]["label"]}**. Latest source fetch: `{manifest["collected_at"]}`.',
             "", f'{len(coverage["requested_subjects"])} requested of {len(coverage.get("discovered_subjects", coverage["requested_subjects"]))} discovered departments; {sum(row["course_count"] for row in coverage["departments"])} course listings; {stats["section_count"]} registration sections; {stats["meeting_count"]} meetings.',
             f'Meetings with missing instructors: {stats["missing_instructor_meetings"]}. Multiple instructors: {stats["multiple_instructor_meetings"]}. Unresolved listed instructor occurrences: {stats["unresolved_occurrences"]}.',
             "", "Counts retain separate registration records and are not unique teaching groups or professors. Missing source labels and empty schedules are explicitly marked, never invented.",
             "", "| Department | Status | Listings | Sections | Meetings | Missing instructors |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for row in coverage["departments"]:
        lines.append(f'| {row["subject"]} | {row["status"]} | {row["course_count"]} | {row["section_count"]} | {row["meeting_count"]} | {row["missing_instructor_meetings"]} |')
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/collection.json"))
    parser.add_argument("--term", help="Override configured current term; must exist in discovered schedules")
    parser.add_argument("--start-year", type=int, help="Override the archive start year")
    parser.add_argument("--reuse-current", action="store_true", help="Integrate already saved schedule; no source requests")
    parser.add_argument("--refresh-history", action="store_true", help="Explicitly refetch normalized historical schedules")
    parser.add_argument("--public-dir", type=Path, default=Path("public/data"))
    add_client_arguments(parser)
    args = parser.parse_args()
    try:
        config = read(args.config)
        if args.term:
            config["current_term"] = args.term
        else:
            require(date.today() <= date.fromisoformat(config["current_term_valid_until"]), "Configured term expired; review collection.json against available schedules")
        if args.start_year is not None:
            config["archive_start_year"] = args.start_year
        inputs = teammate_inputs(config)
        client = CourseExplorerClient.from_args(args)
        previous = {}
        if (args.public_dir / "integration.json").exists():
            _, previous = validate_bundle(args.public_dir)
            source_groups = [previous["schedule"]["sources"], previous["history"]["discovery_sources"]]
            source_groups += [snapshot["sources"] for snapshot in previous["history"]["snapshots"]]
            for source in [source for group in source_groups for source in group]:
                old = client.minimum_fetch_times.get(source["url"])
                client.minimum_fetch_times[source["url"]] = max([old, source["fetched_at"]], key=timestamp) if old else source["fetched_at"]
        require(not (args.reuse_current and args.refresh_history), "--reuse-current cannot refresh history")
        path = Path("data/snapshots/campus-schedule.json")
        if args.reuse_current:
            if (args.public_dir / "integration.json").exists():
                _, previous = validate_bundle(args.public_dir)
                schedule, coverage = previous["schedule"], previous["department_coverage"]
            else:
                require(path.exists(), "No saved current schedule to reuse")
                schedule = read(path)
                coverage = read(path.with_suffix(".coverage.json"))
        else:
            schedule = collect(client, config["current_term"], path)
            coverage = read(path.with_suffix(".coverage.json"))
        validate_department_coverage(schedule, coverage)
        normal_ttl = client.cache_ttl
        if args.refresh_history:
            client.cache_ttl = 0
        history = history_for(config, inputs, client, args.public_dir, args.refresh_history,
                              not args.reuse_current, (schedule, coverage), previous.get("history"))
        client.cache_ttl = normal_ttl
        require(schedule["term"]["id"] == config["current_term"], "Selected term and collected schedule disagree")
        reports = {Path("docs/current-coverage.md"): report_current({"current_term": schedule["term"], "coverage": counts(schedule["sections"]), "collected_at": schedule["collected_at"]}, coverage),
                   Path("docs/integration-history-coverage.md"): render_archive_report(history)}
        old_reports = {path: path.read_text(encoding="utf-8") if path.exists() else None for path in reports}
        try:
            for report_path, body in reports.items():
                atomic_write_text(report_path, body)
            alias_path = Path("data/mappings/course-aliases.json")
            mapping = read(alias_path) if alias_path.exists() else None
            manifest = publish_bundle(args.public_dir, schedule, history, inputs, coverage, reviewed_aliases=mapping)
        except Exception:
            for report_path, body in old_reports.items():
                if body is None:
                    report_path.unlink(missing_ok=True)
                else:
                    atomic_write_text(report_path, body)
            raise
        print(f'Published {manifest["coverage"]["section_count"]} sections; {client.network_requests} network requests; {client.cache_hits} cache hits.')
    except (DataError, OSError, ValueError, KeyError) as error:
        print(f"Update failed; previous published manifest retained: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
