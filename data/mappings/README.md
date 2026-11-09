# Reviewed mappings

**Resumed November 8, 2026:** review the existing RMP candidates and GPA/teaching identity queues, prioritizing high-impact cases. Fall 2026 grades are outside this review. The catalog still displays all collected courses, official faculty-directory identities, and unresolved schedule-name entries, independently of GPA availability. Keep both review queues. The [scope decisions](../../docs/backlog.md) record the clarification and resumption order.

`course-aliases.json` is consumed by the shared publisher. A reviewed entry needs course codes, explicit applicable `term_ids`, review identity/time, and exact official “Same as”/“See” evidence and URL. Automated source relationships are already published with their terms and provenance; reviewed records remain separate and never merge CRNs.

`professor-identities.json` is the identity review workspace. It is not automatically interpreted as verified links. Accepted decisions export to `data/inputs/professors.json` and `verified-links.json` with explicit evidence; uncertain names remain unresolved.

`python3 -m scripts.review_identities --include-archive` compares every GPA source name with official full-name/unit directories and saved course/term occurrences. It writes the ledger, a complete GPA queue (`identity-review.csv`), an archive queue (`archive-identity-review.csv`), and the [coverage report](../../docs/identity-review-coverage.md). GPA decisions come first; archive-only labels remain a separate follow-up queue. A completed comparison can still require more evidence before an identity is verified.

`--apply` exports accepted decisions to the normalized inputs after validating their joins against the saved archive. It rebuilds this review batch's links so new ambiguity withdraws older automatic decisions, while preserving independent reviews. It does not publish. `--reuse-sources` replays saved responses in ignored `.cache/identity-review`; without that flag, missing responses are collected with verified HTTPS and a one-second interval. Existing responses keep their original fetch times. The ledger records source hashes, failures, and GPA/manifest/config/script fingerprints. Public JSON caches retain only the professional identity fields needed for matching.

The rules and individually sourced name variants live in [`config/identity-review.json`](../../config/identity-review.json). A unique full first/surname match needs department evidence and a same-course/term schedule occurrence. Conflicting supplied middle names, multiple official identities, and initials shared with current or historical GPA names stay unresolved. Nicknames and truncated source names require explicit literal review entries. Historical role evidence does not claim current employment. A sole initial-only archive candidate still needs occurrence evidence.

Access-denied directory pages are recorded as failures, never as evidence that a person is absent. Such hosts are deferred for 24 hours; earlier valid saved responses remain usable. Former instructors often require an official historical roster, syllabus, or dated unit page beyond today's directories.

See [the data contract](../../docs/data-contract.md).

## RMP coverage checkpoint

`python3 -m scripts.import_faculty --reuse-sources` adds NetID-backed identities from the saved official campus faculty rollup and Grainger faculty roster independently of GPA availability. It preserves existing IDs/ratings and creates no course or grade links. `faculty-directory-review.json` records the source snapshots, additions, and any unresolved profile-URI/NetID reconciliation. Individually verified teaching additions are documented in `teaching-identity-reviews.json`. These directory-only identities remain protected when the GPA-focused identity export is rebuilt.

`python3 -m scripts.review_rmp` audits the current identified instructor set against the anonymous public RMP UIUC search directory. The identity set is fixed within each run; unresolved schedule-name entries are not rating candidates. It retrieves the site's public aggregate/course fields through its GraphQL endpoint, follows all result pages, checks school identity, and records duplicate result IDs. Requests use a one-second interval and stop on access denial; no login, individual review text, or account data is collected.

Each instructor gets exactly one outcome in `rmp-identities.json` and `rmp-review.csv`: `verified_match`, `ambiguous_candidates`, `no_matching_profile_found`, or `lookup_unavailable`. Matching requires compatible full names, UIUC, and official unit or previously verified course context. `config/rmp-review.json` lists explicit department-label equivalents and reviewed college/department relationships; they never establish name identity. New label reviews retain official source URLs, fetch dates and hashes, and accepted candidates retain the corresponding affiliation evidence. Competing supported profiles remain ambiguous. Nicknames, shortened surnames, multiple supported profiles, and shared profile ownership remain unverified. A no-match outcome is limited to the results returned by this run, not proof that no profile exists. Directory duplicates and limitations are documented in the [report](../../docs/rmp-coverage.md).

Add `--reuse-sources` to replay cached aggregate data in ignored `.cache/rmp-review` without requests. Add `--apply` to export accepted numerical summaries to the existing instructor records; this preserves the instructor set, rebuilds this batch's prior ratings, and refuses to apply incomplete pagination. Independent ratings require explicit reconciliation. Publication is a separate step; review commands do not deploy. The Pages workflow is enabled. Every accepted summary records matching evidence, raw/normalized metrics in the ledger, source timestamps, and retrieval hashes.

## Continued identity evidence

The [follow-up review](../../docs/coverage-expansion-followup-2026-11-08.md) and [follow-up ledger](coverage-expansion-followup.json) record additions after the initial November 8 batch. `rmp-name-reviews.json` records individually sourced published-name forms, also retained in normalized instructor `identity_name_reviews`; the original display name is preserved.

A reviewed `manual_directory_people` entry may provide an official `profile_url` when no NetID is established. Its `directory_id` must be the namespaced SHA-256 URI key, and export retains `directory_profile_url` without fabricating `institutional_id`. Public named teacher/profile links and individual faculty biographies can supply evidence; protected profile contents are not fetched or inferred.

`subject_unit_reviews` requires explicit `added_units`, reviewer, time, source URLs and evidence. Those sources must be available before the additional affiliation is used. Candidate provenance includes the reviewed affiliation sources; access failure removes only the added unit mapping. This does not merge course codes or grades.

RMP name context may reuse exact spellings from independently reviewed GPA bridges, with matching source/grade IDs and identity evidence. Unreviewed grade names never contribute. Explicit parenthetical prefix nicknames such as Timothy (Tim) are distinguished from middle names; actual supplied middle tokens remain checked.
