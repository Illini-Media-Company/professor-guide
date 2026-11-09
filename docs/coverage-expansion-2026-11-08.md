# Coverage review — November 8, 2026

The [continuation report](coverage-expansion-followup-2026-11-08.md) supersedes the current-status and held-case descriptions below. This document preserves the first-pass checkpoint.

Reviewed existing data only. Fall grades were not collected. Deployment remains paused.

## Results

| Coverage | Before | After | Net gain |
| --- | ---: | ---: | ---: |
| Identified instructors | 3,390 | 3,396 | +6 |
| Verified RMP profiles | 1,341 | 1,587 | +246 |
| Numerical RMP ratings | 1,213 | 1,411 | +198 |
| Verified GPA rows | 11,810 | 12,238 | +428 |
| Verified teaching occurrences | 9,061 | 9,168 | +107 |

Of the original 687 ambiguous RMP cases, 252 now have supported profile matches and 435 remain ambiguous. The full current queue contains 444 ambiguous cases, including newly surfaced competing profiles and new identities. There are 254 newly accepted profile matches and eight previously accepted matches returned to pending, for a net gain of 246 profiles. Only profiles with actual ratings add numerical scores.

## Evidence and safeguards

- Reviewed 45 RMP label mappings against official directories, school department lists, and the university catalog. College labels supply affiliation context, never a name alias. Full-name agreement and unique profile ownership remain required.
- Every new mapping has source URLs, collection dates, hashes, reviewer and evidence in `config/rmp-review.json`; accepted candidates retain that evidence in the RMP ledger.
- The six new institutional identities and seven GPA-name recoveries have individually sourced evidence in `config/identity-review.json`. The Thomas J/Thom Miller and truncated Gerlando compound-surname cases are literal reviewed variants, not fuzzy matching rules.
- Two additional Fall 2023 ENG 101 lecture occurrences use the official syllabus and exact BL1/SL1 sections. Discussion staff are excluded; no primary role or GPA is inferred from those links.
- All prior GPA attributions are preserved. The raw grade input and underlying schedule/archive source objects are unchanged. Numerical RMP metrics retain their original retrieval dates; this batch improved matching rather than refreshing rating counts.

## Recovered GPA rows

| Source instructor name | Rows recovered |
| --- | ---: |
| Miller, Thomas J | 103 |
| Soranso, Murillo S | 87 |
| Powers, Kimberly | 81 |
| Clegg, Benjamin F | 47 |
| Augusto Sampaio, Gerlando | 41 |
| Gundersen, Lisa C | 39 |
| Gist, Toni M | 30 |

## Cases still needing evidence

Eight formerly accepted RMP profiles now have competing supported candidates. They remain pending rather than choosing the profile with the most ratings:
- Julie Kraft
- Gagandeep Singh
- Craig Bradshaw
- Eman Saadah
- Karthekeyan Chandrasekaran
- Deana C McDonagh
- Rebecca Weber
- Andrew Edmund Miller

The full [identity report](identity-review-coverage.md) still has 6,386 unresolved GPA rows. Current priorities include Caitlin Clarke (middle-name conflict), Roman Friedman and Mary Licht (historical LAS identity evidence), Jennifer Joesting (official historical identity/course evidence), and Elizabeth Frasca (Beth/Elizabeth identity evidence). Access failures and timeouts were not treated as nonmatches.

The abbreviated-name inventory still has 17,261 unresolved subject/name labels spanning many course/term occurrences. The 107 new verified occurrence links do not establish that each repeated label is one person or fully resolve those labels across all semesters. Additional dated staff pages and syllabi are needed.

## Reproduce and inspect

Use cached source replay:

```sh
python -m scripts.review_identities --reuse-sources --include-archive --apply
python -m scripts.review_rmp --reuse-sources --apply
python -m scripts.update_data --reuse-current
```

Independent syllabus occurrence reviews are already preserved in the normalized links and documented in [the teaching review ledger](../data/mappings/teaching-identity-reviews.json). Raw source caches are ignored; normalized provenance and review decisions are stored in repository files. The [batch ledger](../data/mappings/coverage-expansion-review.json) lists every recovered grade ID, added occurrence ID, new RMP match and reclassified case.

No coverage threshold or deployment decision is assumed.
