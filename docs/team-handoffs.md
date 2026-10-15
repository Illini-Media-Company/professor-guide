# Three ready-to-use teammate tasks

Jon's collector/integration infrastructure is complete independently of these product implementations. Production currently marks all three normalized enrichment inputs pending. The examples under `data/examples/integration/` are synthetic and must not be copied into production as real observations.

## GPA owner task

Implement your grade-source ingestion and GPA calculations. Produce **`data/inputs/gpa.json`** using `data/examples/integration/gpa.json` as the shape, with `data_kind: "live"`, real source URLs/timestamps, and stable record IDs.

Input: the current manifest at `public/data/integration.json`, its `schedule` object, and its `history` object. Every nested Course Explorer snapshot uses the established v1 format. Use `term_id`, `listing_id` (`term:SUBJECT number`), and `section_id` (`term:CRN`) only when the grade source genuinely provides those keys.

Records specify `grain: "section"`, `"course_term"`, or `"instructor_course_term"`; `term_id`, `course_code`, `gpa` (0–4 or null), `student_count` (nonnegative integer or null), and `section_id` (term + CRN only at section grain). For instructor/course/term grades, provide the source's `primary_instructor_name_raw`. Keep section ID null when CRNs are absent. Never spread course-level grades over every section or co-instructor. Unknown values are null; a genuine zero stays zero.

The campus archive already covers every listed course in its configured 2023–2026 range. If your grade source covers older terms, coordinate an explicit archive range extension. A course absent from a term’s official index remains unavailable rather than borrowing another listing’s sections. Professor attribution is added separately only when the source-listed primary name agrees with a verified occurrence link whose primary designation has evidence. A source instructor appearing first is insufficient. Course/term aggregate grades remain unassigned to professors. Cross-listings are separate registration records; define and document your aggregation policy without multiplying samples across aliases.

Completion criteria: real-source normalized output; your grade calculation checks; explicit grain and missing-value rules; source provenance; no fabricated CRNs/identities; `python -m scripts.update_data --reuse-current` and published-data validation pass once required history is available. Do not edit the collector to supply your output.

## Professor matching / RMP / faculty owner task

Implement source-name identity review, numerical RMP collection, and official faculty-link verification. Produce **`data/inputs/professors.json`** and **`data/inputs/verified-links.json`**, following the synthetic examples.

`professors.json` uses `dataset: "professors"` and stable `professor_id`, `display_name`, and `identity_evidence`. Optional RMP summaries specify `scope: "professor"`, `overall_quality` (0–5 or null), `num_ratings`, real `source_url`, and `collected_at`. Faculty links contain a URL, verification evidence, and `verified_at`. Professor-wide ratings stay separate from course grades.

`verified-links.json` uses `dataset: "verified_occurrences"`. Each reviewed link includes `id`, `professor_id`, `listing_id`, `section_id`, `meeting_id`, `instructor_index`, exact `name_raw`, `verified: true`, `verified_at`, evidence, and explicit boolean `is_primary`. A true primary designation requires `primary_evidence`; do not infer it from array order. The publisher verifies that the referenced name/position actually exists on that source meeting and that the professor ID exists in your professor file. A refreshed source can invalidate stale occurrence positions; retain source collection context in your review process.

Leave uncertain identities out of verified links. Original schedule `professor_id` fields stay null; verified links are separate. Preserve initials/source spelling and do not merge people based on shared schedules, cross-listings, or names alone. `data/mappings/professor-identities.json` can remain your review workspace; publication consumes your normalized outputs, not guesses from that file.

Completion criteria: evidence-backed identity review and links; professor-wide numerical summaries with counts/provenance; independently verified faculty URLs; unresolved cases documented; input validation and attribution checks pass; no changes to Jon's collector.

## Frontend owner task

Implement search, filters, results table, professor/course profiles, GPA/rating displays, and charts in `src/`. Extend the data page while preserving the Vite base path and embed behavior.

Entry point: fetch `${import.meta.env.BASE_URL}data/integration.json`. Resolve each `files.NAME.path` relative to `${import.meta.env.BASE_URL}data/`. Available objects include `schedule`, `history`, `aliases`, `department_coverage`, and `attributions`; `gpa`, `professors`, and `verified_occurrences` are explicitly pending until supplied. Keep one manifest's object set together. File SHA-256/byte-size/source timestamps are provided; paths are immutable.

Use term + CRN for section keys and term + course code for listing keys. Keep multiple/missing instructors on individual meetings. Use the separate verified links for real professor profiles; raw source names are unresolved. Use only verified GPA attribution from `attributions.grade_attributions` (or the same documented join policy), preserve the supplied grade grain, and show unavailable data differently from numeric zero. Professor-wide RMP values are not course-specific grades. Alias evidence supports related searchable listings, not duplicate grade samples or merged registration records.

The starter’s `src/data.js` exports `loadGuide(signal)`, returning `{manifest, history}` from one manifest and its small v2 archive index. `App.jsx` displays actual coverage, collection dates, and per-term downloads. Resolve a term’s `snapshot.path` only when its data is needed; do not preload every year into the browser. New work uses the manifest; fixed-name sample exports are retired. Synthetic examples live in `data/examples/` and are exercised by the offline checks; do not publish them as production data.

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
