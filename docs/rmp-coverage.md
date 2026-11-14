# RMP coverage audit

Checked at `2026-11-13T09:58:28Z`.

**1,623 of 3,416 instructors (47.51%)** have a unique supported RMP match.

School-directory coverage: 5,354 of 5354 result entries, representing 5,255 distinct profiles; pagination complete: true.
Repeated profile IDs returned by the directory: 99. Repeated IDs are counted once; conflicting identity fields stop the audit.

| Outcome | Instructors |
| --- | ---: |
| ambiguous_candidates | 428 |
| lookup_unavailable | 0 |
| no_matching_profile_found | 1,365 |
| verified_match | 1,623 |

## Metric availability

| Metric | Matched instructors with a value |
| --- | ---: |
| overall_quality | 1,446 |
| num_ratings | 1,623 |
| difficulty | 1,446 |
| would_take_again_percent | 1,364 |

## Method and limits

The audit compares the fixed accepted instructor set with the public RMP school-directory results for University Of Illinois at Urbana - Champaign. Full-name matches require official department or verified course context. Compatible initials and small surname variants additionally require a shared independently verified teaching course and no competing established identity. Conflicting full first/middle names, multiple supported profiles, and shared profile assignments remain ambiguous.

Full source names from individually reviewed GPA bridges can supplement official directory spellings. These require an exact grade-record/name/source reference and prior identity evidence; unreviewed grade names never participate. The accepted rating retains the spelling review and grade-source provenance separately from the RMP metric source.

These are bulk rule-based matches, not individual manual investigations. RMP course codes are supporting profile context; they do not make its aggregate ratings course-specific. The source is an anonymous query to the same public directory endpoint and pagination interface used by the RMP website, requesting its public profile summary/course fields. No individual review text is collected. Profile URLs identify the rated person; retrieval timestamps and query/response hashes identify where each metric was actually fetched.

Missing values and source sentinel values remain null; a genuine zero-percent take-again value is retained. Rating counts are counts of reviews, not graded enrollments. Failure or incomplete pagination is lookup unavailable, never evidence of absence. A no-match outcome means no name candidate was found in the directory results returned during this run; it does not establish that no profile exists. Repeated result IDs can reflect indexing or changing search order, so pagination completeness does not guarantee an exhaustive list of every real RMP profile.

## Launch checkpoint

Launch decision: proceed with available verified ratings. Missing metrics and unmatched profiles display Pending; there is no minimum coverage requirement. Further GPA/archive identity review is tracked separately.

See the [complete audit queue](../data/mappings/rmp-review.csv) and [evidence ledger](../data/mappings/rmp-identities.json).
