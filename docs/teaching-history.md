# Teaching-history collection and team handoff

The pilot is saved in [`public/data/teaching-history.json`](../public/data/teaching-history.json). Its [generated coverage report](pilot-coverage.md) records ten verified course/term pairs: Fall 2026 teaching assignments and Spring 2025 historical assignments for CS/ECE 374 and CS/STAT/IS 107. These are registration listings and meeting assignments from Course Explorer, not verified professor identities, calculated grades, or unique teaching loads.

## Run it

From the repository root, on this Mac:

```sh
SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m scripts.course_explorer_discovery --years 2025 2026
SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m scripts.collect_teaching_history \
  --terms 2026-fall 2025-spring \
  --courses "CS 374" "ECE 374" "CS 107" "STAT 107" "IS 107" --refresh &&
python3 -m scripts.publish_data --input data/snapshots/teaching-history.json
python3 -m scripts.teaching_history --input public/data/teaching-history.json --output docs/pilot-coverage.md
```

Other systems can normally omit `SSL_CERT_FILE`; configure a trusted local CA bundle if Python needs one. TLS verification remains enabled. The collector defaults to the pilot terms/courses. `--output` selects a candidate path outside `public/`; `--report` selects the latest attempt's Markdown path outside `public/`. Run either collector with `--help` for timeout, retry, cache, and refresh options.

Builds and tests use saved files and require no Course Explorer connection:

```sh
npm run test:data
npm run validate:data
npm run build
```

## Discovery and availability

Discovery follows the actual official XML hierarchy:

1. `/schedule.xml` lists calendar years.
2. `/schedule/YEAR.xml` lists the terms in that year, including their actual official term IDs.
3. `/schedule/YEAR/TERM.xml` lists subjects.
4. `/schedule/YEAR/TERM/SUBJECT.xml` lists course numbers and URLs.
5. A listed course's ordinary and `?mode=detail` XML must agree on section CRNs and labels before its assignments are accepted.

A season is never treated as available just because its name is recognized by the CLI. An absent entry in a successfully parsed parent index is `unavailable`, with reasons `year_not_listed`, `term_not_listed`, `subject_not_listed`, or `course_not_listed`. Coverage retains that index's URL and original fetch time. No invented course record or zero-instructor placeholder is inserted for an absent listing.

Request/HTTP errors are separate from availability. For example, a 404 when fetching a course found in its subject index is a request failure, not proof that the course was never offered. Malformed XML, missing index containers, wrong IDs, and incomplete section details are validation failures. Both kinds produce `error` rows in the local attempt report and a nonzero exit code; neither can be published.

If one pair fails after others succeed, the attempt report shows those successes, but the entire previous history candidate and public bundle are preserved. Review `data/reports/teaching-history-latest-attempt.md` after failures. The public [pilot report](pilot-coverage.md) is generated only from a validated saved bundle and continues to describe its last successful collection.

## Caching and timestamps

Responses from prior calendar years use a 30-day cache by default. The calendar-year list and current-year responses use six hours. This conservative rule avoids guessing the end date of a current-year semester. Customize the TTLs with `--historical-cache-ttl` / `--cache-ttl` in seconds. `--refresh` or `--cache-ttl 0` bypasses both cache tiers.

The cache stores successful XML and its actual fetch timestamp. It never substitutes expired data after a request failure. Cached historical records keep their original timestamps, even when assembled or published later. Semantic validation still runs on cached XML. A repeated cached collection should yield identical JSON bytes and timestamps when no other requests have refreshed the shared cache.

The history-level timestamp is the latest successful discovery or course fetch. Each nested snapshot has its original course-source timestamps, each section uses the detailed response timestamp, and coverage checks have their own `checked_at`. Use the full `sources` / `discovery_sources` arrays to audit freshness, not just the history timestamp. Historical registrar corrections are possible, so run `--refresh` when a new source verification is needed.

## Consume the saved data

The additive history envelope has `dataset: "teaching_history"`, `schema_version: 1`, `requested_terms`, `requested_courses`, `discovery_sources`, `snapshots`, and `coverage`, alongside `data_kind` and `collected_at`. Each item in `snapshots` is exactly the existing v1 Course Explorer format. The original public file and frontend loader retain their previous format.

Read snapshots directly in Python:

```python
import json
from pathlib import Path

history = json.loads(Path("public/data/teaching-history.json").read_text())
for snapshot in history["snapshots"]:
    courses = {course["listing_id"]: course for course in snapshot["courses"]}
    for section in snapshot["sections"]:
        course = courses[section["listing_id"]]
        for meeting in section["meetings"]:
            for instructor_index, instructor in enumerate(meeting["instructors"]):
                occurrence = {
                    "term_id": section["term_id"],
                    "listing_id": course["listing_id"],
                    "course_code": course["course_code"],
                    "section_id": section["id"],
                    "crn": section["crn"],
                    "section_label": section["section_label"],
                    "meeting_id": meeting["id"],
                    "meeting_role": meeting["type"],
                    "instructor_index": instructor_index,
                    "name_raw": instructor["name_raw"],
                    "professor_id": instructor["professor_id"],
                    "source_url": section["source_url"],
                    "collected_at": section["collected_at"],
                }
                # Pass occurrence to your own processing/matching stage.
```

`instructor_index` here is a derived position, not a new field in the public contract. Missing instructor arrays generate no instructor occurrences; inspect `instructor_list_status` and coverage separately so they do not disappear from your completeness analysis.

For frontend integration later, fetch `${import.meta.env.BASE_URL}data/teaching-history.json`. This milestone does not modify the existing demo loader.

### GPA owner

Iterate `snapshots` and join reliable CRN-level grade data with `section.id` (`term_id + CRN`). If a grade source contains no CRN, retain its actual grain and agree on a course/term join with the integration lead. `listing_id` is the course/term key. Cross-listing relationships do not justify merging registration records, copying grades to every alias, or adding duplicate samples. Do not attribute every instructor in a section to every meeting; lecture, online lecture, discussion, and lab/discussion roles are saved separately. Grade calculations and aggregation policy remain yours.

### Matching owner

Use source instructor occurrences with term, listing, section, meeting, and original name context. Initials and raw names are not verified identities. Every collected `professor_id` is `null` and every `match_status` is `unresolved`. Keep raw names and provenance when supplying reviewed matches separately. Multiple instructors on a meeting stay separate, including their original first/last name attributes.

Meeting IDs and instructor positions are scoped to the source snapshot; a registrar edit can reorder them. Include the source collection timestamp when retaining occurrence assignments across refreshes. Do not merge identities from a shared schedule or cross-listing alone. RMP collection, identity verification, and official faculty link verification remain yours.

## Coverage definitions and limits

Coverage contains one term row per requested term and one course row for every requested term/course pair. It distinguishes requested, collected, unavailable, and failed pairs. Section counts include each separate registration listing. Meeting counts can exceed section counts: Spring 2025 CS/ECE 374 each include a section with an additional meeting.

“Missing instructors” counts meetings with an empty or absent instructor list. “Multiple instructors” counts meetings listing more than one instructor. “Unresolved occurrences” counts each listed instructor on each meeting whose professor ID is null; it is not a count of unique people. Validators recompute all counts from the nested snapshots and reject mismatches or missing request pairs.

The pilot has no unavailable pairs and no missing instructor lists. Its 107 records include `LBD` (Laboratory-Discussion), and Spring 2025 374 includes `OLC` (Online Lecture). Codes and labels remain source values. Empty instructor lists and standalone `LAB` meetings are still tested with synthetic fixtures. The collector continues to reject a listed course with no sections or a section with no meetings; such a response is an error pending an explicit empty-state contract, not an unavailable listing.

Current API documentation, rate limits, archive immutability, and service guarantees remain unverified. Discovery describes what Course Explorer listed at the saved fetch time, not every course ever taught. The pilot is deliberately limited to two terms and five registration listings per term.
