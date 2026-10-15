# Data contract v1

The executable contract is `scripts/data_contract.py`; the readable full example is [`data/examples/course-explorer.json`](../data/examples/course-explorer.json). The example is synthetic. Live datasets are resolved through [`public/data/integration.json`](../public/data/integration.json). Original fixed-name snapshot URLs remain available for compatibility.

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

Collection validates the complete requested set before replacing a candidate. Individual-course collection compares index/detail CRN sets; department collection compares index/batch course sets and validates nested sections. The integration publisher validates a complete bundle before switching one manifest atomically; the original single-file publisher remains for compatibility exports. Failures before the switch retain the previous published bytes and timestamps. Source professor matches remain unresolved; verified matching outputs join separately.

## Teaching-history bundle v1 (additive, implemented)

The manifest’s `history` object provides multi-term assignments. `public/data/teaching-history.json` retains the initial pilot for compatibility. Nested snapshots use the original Course Explorer format, with no renamed fields or new professor identity assumptions. The standalone compatibility publisher selects filenames by `dataset` and prevents writing a history bundle over the course snapshot.

| Field | Meaning |
| --- | --- |
| `schema_version`, `dataset`, `data_kind` | `1`, `"teaching_history"`, and `"live"` or `"development_fixture"` |
| `collected_at` | Latest successful fetch among discovery indexes and included course sources; publication does not update it |
| `requested_terms` | Requested term IDs, e.g. `["2026-fall", "2025-spring"]`; presence here does not assert availability |
| `requested_courses` | Requested listing codes applied to every requested term |
| `discovery_sources` | Successful index `{url, fetched_at}` records for year, term, subject, and course availability checks |
| `snapshots` | One original v1 Course Explorer snapshot per term with at least one successfully collected listing |
| `coverage.terms` | Every requested term, availability, reason, index `source_url`, and `checked_at`; available rows also include discovered `term` metadata |
| `coverage.courses` | Every requested term/course pair, availability evidence, and counts derived from its sections |
| `coverage.totals` | Requested/available/collected terms, requested/collected/unavailable/error pairs, and aggregate section/meeting/instructor counts |

Term status is `available` or `unavailable`; course status is `collected` or `unavailable`. Failed attempts additionally use `error` with `error_kind: "request"` or `"validation"` in the local Markdown attempt report, but are rejected by publication. Network/HTTP failures and malformed responses never become unavailable records. Absence must be established by a successfully parsed official parent index, with reasons `year_not_listed`, `term_not_listed`, `subject_not_listed`, or `course_not_listed`.

For collected rows, the reason is `course_listed`; term availability uses `term_listed`. `checked_at` is the index response's original timestamp, including on cache hits. Course availability is normally established from the subject index. If the whole term is unavailable, each affected course row carries that term's absence evidence.

Per-course metrics are `section_count`, `meeting_count`, `missing_instructor_meetings`, `multiple_instructor_meetings`, `instructor_occurrences`, `unresolved_occurrences`, and `meeting_types` (API role code → meeting count). Missing/multiple counts refer to meetings. Unresolved occurrences count each listed instructor on each meeting, not unique people. Counts include separate cross-listed registration records and must not be interpreted as unique teaching loads or grade samples. The validator recomputes metrics and checks every requested term/course pair.

Nested snapshot `requested_courses` means the subset actually collected for that term; the bundle's requested lists and coverage describe the full request, including confirmed absences. An unavailable pair produces no fake course/section record. If no courses in a term are available, it has coverage rows but no invalid empty v1 snapshot. A single request/parsing/validation failure prevents replacement of the entire history candidate. Publishing validates again and atomically replaces one self-contained bundle.

The history-level timestamp can be newer than historical course data because discovery indexes have different cache ages. Audit `discovery_sources`, each snapshot's `sources`, and individual section timestamps for freshness. The prior-year cache defaults to 30 days; current-year responses and the top-level year list default to six hours. `--refresh` bypasses both.

See [operations](operations.md) for commands and [team handoffs](team-handoffs.md) for a reading example and GPA/matching responsibilities. Normalized enrichment inputs are defined below; they do not change source schedule records.

## Ownership and reviewed mappings

Jon owns collection, validation, integration, and publication. The GPA owner supplies normalized grades; the matching owner supplies verified professor records, RMP/faculty summaries, and occurrence links. The frontend owner consumes published files. Detailed tasks and completion criteria are in [team handoffs](team-handoffs.md).

`data/mappings/course-aliases.json` is consumed by publication using the reviewed-alias contract below. `data/mappings/professor-identities.json` is a matching review workspace; it is not automatically treated as verified links. Both start empty. Uncertain identities remain unresolved.

## Campus and integration publication (additive, implemented)

The original v1 `course-explorer.json` and `teaching-history.json` remain intact for existing consumers. New consumers, including the placeholder frontend, resolve the current schedule and history through `integration.json`. The current campus schedule is another v1 Course Explorer snapshot.

Department batches use the live-verified `SUBJECT.xml?mode=cascade` endpoint. Canonical course/section `source_url` and course `detail_source_url` still point to their individual XML resources; they do not claim those resources were separately fetched. Optional `index_response_url` and `detail_response_url` identify the actual department index/batch responses. `sources` contains those actual URLs and fetch times. Sections include `response_source_url` for their batch. Course collection time is the latest index/batch fetch; section collection time is the batch fetch. The validator follows actual response URLs when present and the original course URLs otherwise.

Live campus data includes independent-study sections with missing section labels. `section_label` stays null/empty and `section_label_status` explicitly distinguishes `missing`/`empty`. The batch collector can also preserve explicitly empty detailed-section containers with `schedule_status: "no_sections"`, and empty/missing meeting containers with `meeting_status: "empty"`/`"missing"`; it never invents meetings or instructors. Those empty-container cases are synthetic validation cases; initial campus data had no zero-section courses or zero-meeting sections. The older strict individual-course CLI still rejects unexpected empty details. These additive flags supply the explicit empty-state policy missing from the first pilot.

`integration.json` uses `schema_version: 1`, `dataset: "professor_guide"`, `data_kind`, source-derived `collected_at`, `current_term`, `coverage`, and `files`. An available file entry has `status: "available"`, immutable `path: "objects/<sha256>.json"`, exact `sha256`, `bytes`, and source `collected_at`. Pending entries have `status: "pending"` and null path/hash/size/time. They are not zero observations. Resolve paths relative to `data/` using Vite's base URL.

Objects: `schedule` (v1 snapshot), `history` (v1 teaching-history bundle), `aliases` (explicit source relationships with `applicable_terms`, plus separate reviewed records), `department_coverage`, `preview`, and the optional normalized `gpa`, `professors`, `verified_occurrences`, and `reviewed_aliases` inputs. Source data is not overwritten with verified IDs. The publisher assembles and validates a temporary complete set, promotes immutable files, and switches one manifest last. Consumers must use one manifest's object set together. Hashes, sizes, source timestamps, coverage, and joins are checked offline. After a changed successful publication, only the current and immediately preceding manifests’ objects are retained; older versions remain in Git. Identical republishes retain the previous generation. This retention policy changes no schema, filename, or join key; see [operations](operations.md#publication-and-retention).

### Normalized teammate inputs

Every normalized GPA/professor/link input has `{schema_version: 1, dataset, data_kind, collected_at, sources: [{url, fetched_at}], records}`. Sources require HTTPS and real collection timestamps. `data_kind` is `live` in production; synthetic examples are fixture-labeled and cannot be mixed into production.

GPA records: unique `id`, `term_id`, `course_code`, `grain` (`section`, `course_term`, `instructor_course_term`), `gpa` (finite 0–4 or null), `student_count` (nonnegative integer or null), `section_id` (term + CRN only at section grain), and source `primary_instructor_name_raw` for instructor/course/term grain. Values of zero remain valid. Grades without CRNs cannot claim section-level attribution. The collector derives required historical course/term pairs from this file; the v1 history grid can include additional explicitly reported pairs.

Professor records: stable `professor_id`, `display_name`, `identity_evidence`, optional `faculty_links` with URL/evidence/`verified_at`, and optional `rmp` with `scope: "professor"`, `overall_quality` (0–5 or null), nonnegative `num_ratings`, `source_url`, and `collected_at`. RMP is a professor-wide summary, never a course grade.

Verified occurrence records: unique `id`, `professor_id`, `listing_id`, `section_id`, `meeting_id`, `instructor_index`, exact source `name_raw`, `verified: true`, `verified_at`, evidence, explicit boolean `is_primary`, and `primary_evidence` when true. Referenced professors and source occurrences must exist. A source name mismatch fails publication. Unknown/uncertain matches are omitted, leaving source IDs unresolved. Primary designation is never inferred from instructor order.

`preview.grade_attributions` contains grade ID, listing ID, original grain, professor ID or null, section ID only at actual section grain, and verified/unresolved status. A CRN-less grade can attach only at instructor/course/term grain through the source's named primary instructor and an explicit verified primary link to a listed occurrence in that course/term. Multiple differing professor IDs remain unresolved. Course-term aggregates are not attached to professors. All source records remain separate. See the [team task descriptions](team-handoffs.md) and [synthetic input examples](../data/examples/integration/).

### Reviewed aliases

The publisher now consumes `data/mappings/course-aliases.json`. Its `aliases` array can contain reviewed entries with `course_codes`, explicit `term_ids`, `reviewed_by`, `reviewed_at`, and `evidence: [{text, source_url}]`. Evidence must contain explicit “Same as”/“See” text from an official Illinois URL. Reviewed entries remain separate from automatically extracted source edges in `aliases.reviewed_records`; no registration records are merged. The current reviewed array is empty because the live source edges already provide the collected aliases. Professor identity review workspace files remain separate; publication uses normalized verified occurrence outputs.
