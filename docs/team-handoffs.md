# Three ready-to-use teammate tasks

**Scope decision, November 6, 2026:** move forward with the 2,287 identified instructors and 11,810 supported GPA attributions. Further GPA and archive-only identity review is **do later**, and does not block development with this set. Preserve the unresolved queues for resuming GPA review first, then archive-only review. See the [backlog](backlog.md).

**November 7 clarification:** display all collected courses and recorded teaching names regardless of GPA, with official directory-only faculty profiles also searchable. Preserve the existing verified GPA links; unreviewed initials remain subject-scoped schedule-name entries with identity/metrics Pending. The visitor index is version 2 and course availability is independent of reviewed instructor links. No automatic initial expansion is authorized by this visibility change.

Jon's collector/integration infrastructure is complete independently of these product implementations. The prepared publication includes all three normalized enrichment inputs and a compact visitor index. Further identity expansion is deferred, and missing RMP data displays Pending. The examples under `data/examples/integration/` are synthetic and must not be copied into production as real observations.

**November 8 coverage review:** existing-data identity work resumed. The first batch adds 428 verified GPA rows, 107 verified teaching occurrences, and a net 198 numerical RMP ratings. The [batch report](coverage-expansion-2026-11-08.md) records evidence, eight reclassified RMP matches, and remaining queues. Fall grade collection and deployment remain paused.

**Coverage continuation:** the [follow-up report](coverage-expansion-followup-2026-11-08.md) records another 520 GPA rows, 226 teaching occurrences, and 19 numerical RMP ratings. The current prepared index has 3,407 identified instructors and 12,758 verified GPA rows. Original source grades and prior accepted links remain intact.

## GPA owner task

Implement your grade-source ingestion and GPA calculations. Produce **`data/inputs/gpa.json`** using `data/examples/integration/gpa.json` as the shape, with `data_kind: "live"`, real source URLs/timestamps, and stable record IDs.

Input: the current manifest at `public/data/integration.json`, its `schedule` object, and its `history` object. Every nested Course Explorer snapshot uses the established v1 format. Use `term_id`, `listing_id` (`term:SUBJECT number`), and `section_id` (`term:CRN`) only when the grade source genuinely provides those keys.

Records specify `grain: "section"`, `"course_term"`, or `"instructor_course_term"`; `term_id`, `course_code`, `gpa` (0–4 or null), `student_count` (nonnegative integer or null), and `section_id` (term + CRN only at section grain). For instructor/course/term grades, provide the source's `primary_instructor_name_raw`. Keep section ID null when CRNs are absent. Never spread course-level grades over every section or co-instructor. Unknown values are null; a genuine zero stays zero.

The campus archive already covers every listed course in its configured 2023–2026 range. If your grade source covers older terms, coordinate an explicit archive range extension. A course absent from a term’s official index remains unavailable rather than borrowing another listing’s sections. Professor attribution is added separately through a verified occurrence with primary evidence: either an exact source-name match or a reviewed `grade_name_matches` bridge for that GPA row. Preserve full grade-source names even when schedules use initials; the matching owner supplies the bridge. A source instructor appearing first is insufficient. Course/term aggregate grades remain unassigned to professors. Cross-listings are separate registration records; define and document your aggregation policy without multiplying samples across aliases.

Completion criteria: real-source normalized output; your grade calculation checks; explicit grain and missing-value rules; source provenance; no fabricated CRNs/identities; `python -m scripts.update_data --reuse-current` and published-data validation pass once required history is available. Do not edit the collector to supply your output.

## Professor matching / RMP / faculty owner task

Implement source-name identity review, numerical RMP collection, and official faculty-link verification. Produce **`data/inputs/professors.json`** and **`data/inputs/verified-links.json`**, following the synthetic examples.

`professors.json` uses `dataset: "professors"` and stable `professor_id`, `display_name`, and `identity_evidence`. Optional RMP summaries specify `scope: "professor"`, `overall_quality` (0–5 or null), `num_ratings`, real `source_url`, and `collected_at`. Faculty links contain a URL, verification evidence, and `verified_at`. Professor-wide ratings stay separate from course grades.

`verified-links.json` uses `dataset: "verified_occurrences"`. Each reviewed link includes `id`, `professor_id`, `listing_id`, `section_id`, `meeting_id`, `instructor_index`, exact `name_raw`, `verified: true`, `verified_at`, evidence, and explicit boolean `is_primary`. A true primary designation requires `primary_evidence`; do not infer it from array order. The publisher verifies that the referenced name/position actually exists on that source meeting and that the professor ID exists in your professor file. A refreshed source can invalidate stale occurrence positions; retain source collection context in your review process.

When grade and schedule name formats differ, add `grade_name_matches` to that verified occurrence. Review each GPA row's full source name against the faculty identity and source occurrence; record its exact `grade_record_id`, `primary_instructor_name_raw`, grade `source_url`, reviewer, verification time, identity `evidence`, and separate `primary_evidence`. Include the grade URL/fetch time in the link envelope's `sources` too. Use the grade source's explicit primary label as evidence at its actual grain; a sole schedule instructor does not itself establish primary status. Keep occurrence `is_primary: false` when no section-primary designation is established. The bridge supplies primary evidence only for its reviewed grade row. See the [synthetic example](../data/examples/integration/README.md#reviewing-different-source-names). No initial expansion or fuzzy matching is automatic. A new GPA snapshot changes row IDs and requires renewed reviews; stale references stop publication. Conflicting professor identities remain unresolved.

Leave uncertain identities out of verified links. Original schedule `professor_id` fields stay null; verified links are separate. Preserve initials/source spelling and do not merge people based on shared schedules, cross-listings, or names alone. `data/mappings/professor-identities.json` can remain your review workspace; publication consumes your normalized outputs, not guesses from that file.

The implemented campus review is `python3 -m scripts.review_identities --include-archive`. Add `--reuse-sources` for an offline replay of saved official responses and `--apply` to validate/export accepted GPA decisions. Review all GPA names first, then the archive-only queue. The [coverage report](identity-review-coverage.md) and complete [GPA](../data/mappings/identity-review.csv) and [archive](../data/mappings/archive-identity-review.csv) queues record remaining work. Directory gaps and access failures require further evidence; they are not verified nonmatches. See [review workflow details](../data/mappings/README.md). These commands do not deploy.

Completion criteria: evidence-backed identity review and links; professor-wide numerical summaries with counts/provenance; independently verified faculty URLs; unresolved cases documented; input validation and attribution checks pass; no changes to Jon's collector.

## Frontend owner task

Implement search, filters, results table, professor/course profiles, GPA/rating displays, and charts in `src/`. Extend the data page while preserving the Vite base path and embed behavior.

Entry point: fetch `${import.meta.env.BASE_URL}data/integration.json`. Resolve each `files.NAME.path` relative to `${import.meta.env.BASE_URL}data/`. Available objects include `schedule`, `history`, `aliases`, `department_coverage`, `attributions`, and the supplied enrichment inputs. The optional `guide` entry is the compact visitor projection used by the interface. Keep one manifest's object set together. File SHA-256/byte-size/source timestamps are provided; paths are immutable.

Use term + CRN for section keys and term + course code for listing keys. Keep multiple/missing instructors on individual meetings. Use the separate verified links for real professor profiles; raw source names are unresolved. Use only verified GPA attribution from `attributions.grade_attributions` (or the same documented join policy), preserve the supplied grade grain, and show unavailable data differently from numeric zero. Professor-wide RMP values are not course-specific grades. Alias evidence supports related searchable listings, not duplicate grade samples or merged registration records.

`src/data.js` exports `loadGuide(signal)`, returning `{manifest, index}` from one manifest and its compact `files.guide` projection. The interface provides professor/course search, subject/semester filters, a results/detail split on desktop, a separate detail view on phones, per-course weighted GPA/history, and professor-wide RMP summaries with Pending states. It checks the downloaded index's exact hash and byte count. Raw archive and enrichment datasets are source/download links rather than startup requests. Synthetic examples stay in `data/examples/` and are never published as real observations.

Use query strings or hash navigation; GitHub Pages has no history-route fallback. Preserve iframe access, keyboard controls, narrow widths, and the external full-page link. Fixed 800px iframe height is the current handoff. Dynamic resize is unnecessary for this shell; any future resize protocol must validate origin, source window, finite bounded height, and parent-side origin allowlist.

Completion criteria: the full requested interface, explicit loading/error/pending/zero states, source freshness links, correct joins, and passing `npm run build`, `npm run test:embed`, and published-data checks. Coordinate schema changes through `docs/data-contract.md` rather than changing saved JSON ad hoc.

## Read the published data

Load one semester at a time from the repository root. The helper checks the manifest/index references, exact hash, and unchanged v1 schedule schema without network requests:

```python
from scripts.integration import load_term

snapshot = load_term("public/data", "2023-spring")
for section in snapshot["sections"]:
    for meeting in section["meetings"]:
        for index, instructor in enumerate(meeting["instructors"]):
            occurrence = {
                "term_id": section["term_id"],
                "listing_id": section["listing_id"],
                "course_code": section["course_code"],
                "section_id": section["id"],
                "crn": section["crn"],
                "meeting_id": meeting["id"],
                "meeting_role": meeting["type"],
                "instructor_index": index,
                "instructor": instructor,
                "source_url": section["source_url"],
                "collected_at": section["collected_at"],
            }
            # Pass occurrence to your own processing/review stage.
```

For a complete integrity check or existing all-term Python processing, `validate_bundle("public/data")` returns `(manifest, files)` with `files["history"]["snapshots"]` materialized. It reads all archived terms, so prefer `load_term` when processing individual semesters. The current `files.schedule` takes precedence over any archived copy of the same term.

An empty instructor list produces no occurrence; use `instructor_list_status` and coverage when assessing missing assignments. Meeting IDs and instructor positions identify occurrences within a snapshot and may change after source edits. Preserve the collection context when retaining reviews.

[History coverage](integration-history-coverage.md) records the actual archived terms and completeness. Configured dates or discovered availability alone do not establish successful collection.
