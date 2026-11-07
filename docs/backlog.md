# Project backlog and scope decisions

## 2026-11-06: Proceed with the current instructor set

Decision: move forward with the **2,287 identified instructors** in the normalized inputs, supporting **11,810 GPA record attributions**. Further identity expansion is **do later** and does not block the next phase of the guide.

These counts come from the November 2 review. They describe the prepared inputs; publishing them to the live guide is a separate integration/deployment step. “Instructors” includes professors, lecturers, and teaching assistants.

### Do later: remaining identity review

- Investigate the **1,630 unresolved GPA name labels**. Across all names, **6,814 GPA rows** still lack accepted attribution.
- After the GPA review, investigate archive-only instructors. The archive queue contains **17,352 subject/name pairs**, including **13,280** without matching GPA surname/initial context. These labels are not counts of distinct people.
- Use additional official historical rosters, syllabi, and department evidence to resolve missing or ambiguous identities. Retain unresolved records and their evidence; do not force matches to increase coverage.

Resume from the [coverage report](identity-review-coverage.md), [complete GPA queue](../data/mappings/identity-review.csv), and [complete archive queue](../data/mappings/archive-identity-review.csv). The [review workflow](../data/mappings/README.md) documents how to validate and export new accepted decisions.

Current priority: commit and push the attribution implementation, accepted instructor inputs, and preserved review queues, then continue developing the guide with this instructor set.
