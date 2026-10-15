# Public data contract

The executable contract is `scripts/data_contract.py`; the readable full example is [`data/examples/course-explorer.json`](../data/examples/course-explorer.json). The example is synthetic. Live datasets are resolved through [`public/data/integration.json`](../public/data/integration.json). Production consumers use the manifest. The v1 course/section record format is preserved; the historical envelope is now a v2 per-term index.

## Course Explorer snapshot (implemented)

One JSON file contains the complete requested set for one term. Strings are source text unless described otherwise. Optional source fields are `null` when absent and `""` when present but empty. Arrays preserve source order. Time strings and meeting type codes remain exactly as supplied; no timezone or registration linkage is inferred from them.

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1`; coordinate breaking changes with all owners |
| `dataset` | `"course_explorer"` |
| `data_kind` | `"live"` or `"development_fixture"` |
| `collected_at` | Latest successful source fetch timestamp in this snapshot, UTC ISO 8601 |
| `term` | `{id, year, season, source_term_id, label}`; e.g. `id: "2026-fall"`, official `source_term_id: "120268"` |
| `requested_courses` | Exact set of requested course codes, e.g. `["CS 374", "ECE 374"]` |
| `sources` | `{url, fetched_at}` for actual fetched responses (course index/detail or department index/batch); cache hits keep the original time |
| `courses` | Related searchable catalog/registration listings, each kept separately |
| `sections` | Registration records, keyed by term + CRN |
| `relationships` | Directed “Same as” / “See” edges with source evidence |

### Course listing

- `course_code`: subject and number separated by one space, e.g. `"CS 374"`.
- `listing_id`: `"2026-fall:CS 374"`; `term_id`: `"2026-fall"`.
- `title`, `description`, `course_section_information`, `credit_hours`: source fields, without trying to parse prerequisite semantics.
- `source_url`, `detail_source_url`, `collected_at`: course provenance; collection time is the latest index/detail fetch.
- `section_ids`: only this listing's registration records. Never copy sections from an alias.

### Section and meetings

A section includes `id`, `term_id`, `crn` (a string), `listing_id`, `course_code`, `section_label`, `source_url`, `collected_at`, `section_text`, `section_notes`, `status_code`, `part_of_term`, `start_date`, `end_date`, and `meetings`.

**Section ID = term + CRN**, e.g. `"2026-fall:66445"`. A CRN alone is not a stable key across terms. The section timestamp is the detailed response's original fetch timestamp; its source URL points to the individual section XML.

Each meeting has:

```json
{
  "id": "2026-fall:10001:0",
  "source_meeting_id": "0",
  "type": {"code": "LEC", "label": "Lecture"},
  "start": "11:00AM",
  "end": "12:15PM",
  "days_of_week": "TR",
  "room": "100",
  "building": "Example Hall",
  "instructor_list_status": "listed",
  "instructors": [
    {
      "name_raw": "Example, Alex",
      "first_name_raw": "Alex",
      "last_name_raw": "Example",
      "professor_id": null,
      "match_status": "unresolved"
    }
  ]
}
```

This fragment is synthetic. Meeting IDs append the zero-based source order to the section ID; they identify a meeting within a snapshot and are not promised stable across schedule changes. Keep `source_meeting_id` for provenance. A section may contain multiple meeting types with different instructors. Do not flatten instructors onto a whole course or assume a lab instructor teaches the lecture. `LEC`, `LAB`, and `DIS` are distinct; unfamiliar nonempty API codes are preserved too.

`instructors: []` with `instructor_list_status: "empty"` means `<instructors/>` exists; `"missing"` means that container is absent. Multiple listed instructors remain separate, in order. `name_raw` keeps source spelling, punctuation, and initials, with outer whitespace trimmed. Blank instructor elements fail validation rather than disappearing silently.

### Cross-listing evidence

`relationships` contains `{from_listing_id, to_course_code, to_listing_id, relation, evidence}`. `relation` is `"same_as"` or `"see"`. The target ID is `null` if that related course was not requested. Each evidence entry includes the exact `text`, `source_field`, and `source_url`; the source timestamp is available in `sources` and on the course listing.

The conservative extractor recognizes explicit punctuated sentence directives such as `Same as ECE 374.` and `See CS 374.` in `description` or `courseSectionInformation`. Compound directives listing full course codes are supported. References embedded in prerequisite prose are skipped. Other prose remains in the saved source text for review. A relationship does not establish that two particular registration sections meet together, and it never merges CRNs or GPA counts. Shared times, instructors, rooms, course numbers, and prerequisites do not create relationships.

### Refresh and publication boundary

Collection validates the complete requested set before replacing a candidate. Individual-course collection compares index/detail CRN sets; department collection compares index/batch course sets and validates nested sections. The integration publisher validates a complete bundle before switching one manifest atomically. Failures before the switch retain the previous published bytes and timestamps. Source professor matches remain unresolved; verified matching outputs join separately.

## Teaching-history archive v2

`files.history` resolves to a small object with `schema_version: 2`, `dataset: "teaching_history"`, `data_kind: "live"`, `collected_at`, `start_year`, `through_term`, `requested_terms`, `discovery_sources`, and `coverage`.

Every winter, spring, summer, and fall from `start_year` through the configured end term has a row in `coverage.terms`, in calendar order. A row contains:

- `term_id`, `status` (`collected` or confirmed `unavailable`), `reason`, official index `source_url`, and original `checked_at`.
- `term` metadata for collected terms.
- `department_count`, `course_count`, `section_count`, `meeting_count`, `missing_instructor_meetings`, `multiple_instructor_meetings`, `instructor_occurrences`, `unresolved_occurrences`, and `meeting_types`.
- `snapshot` and `department_coverage` object references for collected terms; both are null for unavailable terms. References use the same `status`, `path`, `sha256`, `bytes`, and `collected_at` fields as manifest entries. Paths are relative to `data/`, not to the index file’s `objects/` directory.

Each `snapshot` is a complete original v1 Course Explorer snapshot for one term. Each department-coverage object records `term_id`, all `discovered_subjects`, matching `requested_subjects`, and a `departments` array with status/counts for every department. All listed courses and their separate registration records must be represented. No whole-campus archive is constructed from only a few selected courses.

`coverage.totals` sums listing, section, meeting, instructor, and department counts, and reports requested/collected/unavailable term counts. Department totals are department/term occurrences, not distinct department names. Unresolved occurrences are listed names on meetings, not unique people. Missing and multiple instructor counts refer to meetings; no placeholder person is created for an empty list.

Unavailable terms require a successfully parsed official year/root index and reasons `term_not_listed` or `year_not_listed`. A missing department or course is assessed against its successful term/department index. HTTP/network failures, access challenges, malformed XML, and incomplete department batches are errors; they cannot be published as unavailable. A failed term prevents the entire refresh from replacing the previous manifest and timestamps.

The archive’s timestamp is the latest successful discovery or schedule fetch. Term references retain actual schedule-source timestamps even when a newer archive index is assembled. Source URLs and timestamps remain on every schedule, course, and section. Historical data is reusable, not assumed immutable; `--refresh-history` explicitly recollects it.

### Migration from the earlier milestone

The old v1 history envelope embedded all `snapshots` and a selected-course × term coverage grid in one file. That remains supported for isolated investigation fixtures and reading earlier commits, but is not the production archive format. Several years of campus records are split to avoid a giant browser download and GitHub’s per-file limit.

New consumers resolve `files.history`, then the requested term’s `snapshot` reference. Python `load_term("public/data", "2023-spring")` loads and validates one term. `validate_bundle()` still returns a materialized history with `snapshots` for existing Python processing code, while validating every nested hash. The old fixed-name sample exports are retired from production. `files.preview` is replaced by `files.attributions`, with `dataset: "grade_attributions"`; its actual attribution rules and source join keys are unchanged. The top-level manifest and all course/section records remain version 1.

## Ownership and reviewed mappings

Jon owns collection, validation, integration, and publication. The GPA owner supplies normalized grades; the matching owner supplies verified professor records, RMP/faculty summaries, and occurrence links. The frontend owner consumes published files. Detailed tasks and completion criteria are in [team handoffs](team-handoffs.md).

`data/mappings/course-aliases.json` is consumed by publication using the reviewed-alias contract below. `data/mappings/professor-identities.json` is a matching review workspace; it is not automatically treated as verified links. Both start empty. Uncertain identities remain unresolved.

## Campus and integration publication (additive, implemented)

All current and historical production data is resolved through `integration.json`. The current campus schedule and each archived semester use the v1 Course Explorer format. The data page displays actual coverage and per-term downloads without hard-coded course samples.

Department batches use the live-verified `SUBJECT.xml?mode=cascade` endpoint. Canonical course/section `source_url` and course `detail_source_url` still point to their individual XML resources; they do not claim those resources were separately fetched. Optional `index_response_url` and `detail_response_url` identify the actual department index/batch responses. `sources` contains those actual URLs and fetch times. Sections include `response_source_url` for their batch. Course collection time is the latest index/batch fetch; section collection time is the batch fetch. The validator follows actual response URLs when present and the original course URLs otherwise.

Live campus data includes independent-study sections with missing section labels. `section_label` stays null/empty and `section_label_status` explicitly distinguishes `missing`/`empty`. The batch collector can also preserve explicitly empty detailed-section containers with `schedule_status: "no_sections"`, and empty/missing meeting containers with `meeting_status: "empty"`/`"missing"`; it never invents meetings or instructors. Those empty-container cases are synthetic validation cases; initial campus data had no zero-section courses or zero-meeting sections. The older strict individual-course CLI still rejects unexpected empty details. These additive flags supply the explicit empty-state policy missing from the first pilot.

`integration.json` uses `schema_version: 1`, `dataset: "professor_guide"`, `data_kind`, source-derived `collected_at`, `current_term`, `coverage`, and `files`. An available file entry has `status: "available"`, immutable `path: "objects/<sha256>.json"`, exact `sha256`, `bytes`, and source `collected_at`. Pending entries have `status: "pending"` and null path/hash/size/time. They are not zero observations. Resolve paths relative to `data/` using Vite's base URL.

Objects: `schedule` (v1 snapshot), `history` (v2 archive index), `aliases` (explicit source relationships with `applicable_terms`, plus separate reviewed records), `department_coverage`, `attributions`, and the optional normalized `gpa`, `professors`, `verified_occurrences`, and `reviewed_aliases` inputs. Source data is not overwritten with verified IDs. The publisher assembles and validates a temporary complete set, promotes immutable files, and switches one manifest last. Consumers must use one manifest's object set together. Hashes, sizes, source timestamps, coverage, and joins are checked offline. After a changed successful publication, only the current and immediately preceding manifests’ objects are retained; older versions remain in Git. Identical republishes retain the previous generation. Nested term snapshot and coverage objects are protected by the same retention rule; see [operations](operations.md#publication-and-retention).

### Normalized teammate inputs

Every normalized GPA/professor/link input has `{schema_version: 1, dataset, data_kind, collected_at, sources: [{url, fetched_at}], records}`. Sources require HTTPS and real collection timestamps. `data_kind` is `live` in production; synthetic examples are fixture-labeled and cannot be mixed into production.

GPA records: unique `id`, `term_id`, `course_code`, `grain` (`section`, `course_term`, `instructor_course_term`), `gpa` (finite 0–4 or null), `student_count` (nonnegative integer or null), `section_id` (term + CRN only at section grain), and source `primary_instructor_name_raw` for instructor/course/term grain. Values of zero remain valid. Grades without CRNs cannot claim section-level attribution. The archive independently covers all listed courses in its configured date range. A grade outside that range needs a reviewed range extension; course/term or professor joins that cannot be established remain unresolved.

Professor records: stable `professor_id`, `display_name`, `identity_evidence`, optional `faculty_links` with URL/evidence/`verified_at`, and optional `rmp` with `scope: "professor"`, `overall_quality` (0–5 or null), nonnegative `num_ratings`, `source_url`, and `collected_at`. RMP is a professor-wide summary, never a course grade.

Verified occurrence records: unique `id`, `professor_id`, `listing_id`, `section_id`, `meeting_id`, `instructor_index`, exact source `name_raw`, `verified: true`, `verified_at`, evidence, explicit boolean `is_primary`, and `primary_evidence` when true. Referenced professors and source occurrences must exist. A source name mismatch fails publication. Unknown/uncertain matches are omitted, leaving source IDs unresolved. Primary designation is never inferred from instructor order.

`attributions.grade_attributions` contains grade ID, listing ID, original grain, professor ID or null, section ID only at actual section grain, and verified/unresolved status. A CRN-less grade can attach only at instructor/course/term grain through the source's named primary instructor and an explicit verified primary link to a listed occurrence in that course/term. Multiple differing professor IDs remain unresolved. Course-term aggregates are not attached to professors. All source records remain separate. See the [team task descriptions](team-handoffs.md) and [synthetic input examples](../data/examples/integration/).

### Reviewed aliases

The publisher now consumes `data/mappings/course-aliases.json`. Its `aliases` array can contain reviewed entries with `course_codes`, explicit `term_ids`, `reviewed_by`, `reviewed_at`, and `evidence: [{text, source_url}]`. Evidence must contain explicit “Same as”/“See” text from an official Illinois URL. Reviewed entries remain separate from automatically extracted source edges in `aliases.reviewed_records`; no registration records are merged. The current reviewed array is empty because the live source edges already provide the collected aliases. Professor identity review workspace files remain separate; publication uses normalized verified occurrence outputs.
