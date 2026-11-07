# Reviewed mappings

**Do later (November 6, 2026):** further identity expansion is deferred. Proceed with the current 2,287 identified instructors and retain both unresolved queues. The [scope decision](../../docs/backlog.md) records the counts and resumption order.

`course-aliases.json` is consumed by the shared publisher. The array starts empty. A reviewed entry needs course codes, explicit applicable `term_ids`, review identity/time, and exact official “Same as”/“See” evidence and URL. Automated source relationships are already published with their terms and provenance; reviewed records remain separate and never merge CRNs.

`professor-identities.json` is the matching owner's review workspace. It is not automatically interpreted as verified identity links. That owner produces `data/inputs/professors.json` and `verified-links.json` with explicit evidence; uncertain names remain unresolved.

`python3 -m scripts.review_identities --include-archive` compares every GPA source name with official full-name/unit directories and saved course/term occurrences. It writes the ledger, a complete GPA queue (`identity-review.csv`), an archive queue (`archive-identity-review.csv`), and the [coverage report](../../docs/identity-review-coverage.md). GPA decisions come first; archive-only labels remain a separate follow-up queue. A completed comparison can still require more evidence before an identity is verified.

`--apply` exports accepted decisions to the normalized inputs after validating their joins against the saved archive. It rebuilds this review batch's links so new ambiguity withdraws older automatic decisions, while preserving independent reviews. It does not publish. `--reuse-sources` replays saved responses in ignored `.cache/identity-review`; without that flag, missing responses are collected with verified HTTPS and a one-second interval. Existing responses keep their original fetch times. The ledger records source hashes, failures, and GPA/manifest/config/script fingerprints. Public JSON caches retain only the professional identity fields needed for matching.

The rules and individually sourced name variants live in [`config/identity-review.json`](../../config/identity-review.json). A unique full first/surname match needs department evidence and a same-course/term schedule occurrence. Conflicting supplied middle names, multiple official identities, and initials shared with current or historical GPA names stay unresolved. Nicknames and truncated source names require explicit literal review entries. Historical role evidence does not claim current employment. A sole initial-only archive candidate still needs occurrence evidence.

Access-denied directory pages are recorded as failures, never as evidence that a person is absent. Such hosts are deferred for 24 hours; earlier valid saved responses remain usable. Former instructors often require an official historical roster, syllabus, or dated unit page beyond today's directories.

See [the implemented contract](../../docs/data-contract.md) and [team handoffs](../../docs/team-handoffs.md).
