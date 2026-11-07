# RMP coverage audit

Checked at `2026-11-07T09:55:22Z`.

**1,341 of 3,390 instructors (39.56%)** have a unique supported RMP match.

School-directory coverage: 5,354 of 5354 result entries, representing 5,255 distinct profiles; pagination complete: true.
Repeated profile IDs returned by the directory: 99. Repeated IDs are counted once; conflicting identity fields stop the audit.

| Outcome | Instructors |
| --- | ---: |
| ambiguous_candidates | 687 |
| lookup_unavailable | 0 |
| no_matching_profile_found | 1,362 |
| verified_match | 1,341 |

## Metric availability

| Metric | Matched instructors with a value |
| --- | ---: |
| overall_quality | 1,213 |
| num_ratings | 1,341 |
| difficulty | 1,213 |
| would_take_again_percent | 1,170 |

## Method and limits

The audit compares the fixed accepted instructor set with the public RMP school-directory results for University Of Illinois at Urbana - Champaign. A match requires a compatible full first/surname, compatible supplied middle names, the correct school, and official department or verified course context. Initial-only and nickname candidates require further review; multiple supported profiles and shared profile assignments remain ambiguous.

These are bulk rule-based matches, not individual manual investigations. RMP course codes are supporting profile context; they do not make its aggregate ratings course-specific. The source is an anonymous query to the same public directory endpoint and pagination interface used by the RMP website, requesting its public profile summary/course fields. No individual review text is collected. Profile URLs identify the rated person; retrieval timestamps and query/response hashes identify where each metric was actually fetched.

Missing values and source sentinel values remain null; a genuine zero-percent take-again value is retained. Rating counts are counts of reviews, not graded enrollments. Failure or incomplete pagination is lookup unavailable, never evidence of absence. A no-match outcome means no name candidate was found in the directory results returned during this run; it does not establish that no profile exists. Repeated result IDs can reflect indexing or changing search order, so pagination completeness does not guarantee an exhaustive list of every real RMP profile.

## Launch checkpoint

Launch decision: proceed with available verified ratings. Missing metrics and unmatched profiles display Pending; there is no minimum coverage requirement. Deployment remains paused. Wider GPA/archive identity expansion remains deferred.

See the [complete audit queue](../data/mappings/rmp-review.csv) and [evidence ledger](../data/mappings/rmp-identities.json).
