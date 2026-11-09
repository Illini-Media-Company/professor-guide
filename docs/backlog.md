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

## 2026-11-07: RMP audit before deciding launch coverage

The instructor implementation was merged in PR #3. The Pages workflow is manually disabled. Current checkpoint: audit RMP coverage for the fixed 2,287 instructors and report overall rating, number of ratings, difficulty, and would-take-again percentage. No minimum coverage has been chosen. Stop after the [coverage report](rmp-coverage.md) to decide the launch requirement with the user; deployment remains paused.

Design decisions already agreed: Salary Guide's Gibson typography, white panels, black text, DI orange, gray borders and rounded corners; search first; professors plus connected courses; results beside details on desktop and a separate detail view with Back to results on phones; course-specific GPA and semester history with graded-enrollment counts; the same 800px Daily Illini iframe. Dedicated instructor comparison is deferred.

**Launch decision:** proceed with the accepted instructor set and available verified RMP summaries. Missing ratings or individual metrics display **Pending** and do not block inclusion or launch. No minimum RMP coverage is required. The agreed search/detail interface can proceed; deployment remains paused until separately resumed.

Implemented locally: professor/course search, subject and semester filters, desktop split panels, mobile detail/back navigation, per-course GPA summaries and semester charts, RMP summaries and Pending states, source links and downloads. The prepared publication contains a compact visitor index for the 2,287 instructors and 2,478 connected courses. Deployment remains manually disabled; the local interface is ready for review.

## Catalog coverage correction

The user clarified that the examples of ECE 374 and Emily Fox indicate a general coverage issue: courses and recorded teaching assignments must appear independently of GPA availability or completed identity matching. This supersedes the earlier connected-courses-only browsing scope. List every collected course/semester and all recorded schedule names. Missing grades/ratings remain Pending; unresolved initials remain clearly labeled source-name entries rather than invented person identities. A source-name entry is scoped to a subject and may describe different people across semesters. No source-name entry inherits a named person's GPA or RMP data.

The accepted GPA joins remain unchanged. Emily Kyle Fox was independently reviewed using her official university faculty profile and the Fall 2026 CS/ECE 374 A staff page, with four separately reviewed CS/ECE lecture/recitation occurrences and no inferred GPA. Wider identity resolution remains deferred; visibility of the records we already have does not.

Official campus/Grainger faculty-directory records are also included independently of GPA membership. The saved rosters supplied 1,102 additional NetID-backed faculty identities, bringing identified profiles to 3,390. Their course links and metrics remain pending unless independently supported. Directory membership never expands a schedule initial into a named person's teaching assignment. The complete catalog has 8,371 courses and 17,261 unresolved subject/name entries, accounting for every one of the 148,778 source instructor occurrences.

## Current interface and prepared coverage

The prepared visitor index now includes 3,390 identified instructors, 8,371 courses, and 17,261 unresolved subject/name entries. It retains 11,810 verified GPA attributions. RMP review supports 1,341 profile matches, including 1,213 with numerical overall ratings; see the [current audit](rmp-coverage.md).

Before a text search, instructor browsing puts entries with numerical RMP ratings first, then pending entries. Each group is alphabetical by last name, including under subject and semester filters. Text searches retain all matching listings. A small chart icon beside a name indicates usable verified GPA data within the selected subject/semester scope, without a legend. The interface uses the Salary Guide's Gibson font kit, orange, gray borders, and panel/table styles, with repeated methodology text kept under About the data.

Desktop details remain beside results; phones retain the detail view and Back to results. The proposed change to keep mobile results and details visible together was withdrawn. The Pages workflow remains manually disabled; committing and pushing this work does not resume deployment.

## November 8, 2026: Resume existing-data coverage review

The user resumed review of the 687 RMP candidate cases, 6,814 unresolved GPA rows, and abbreviated teaching names. Fall grades remain outside scope; deployment stays paused.

The first evidence-backed batch resolves 252 of the original RMP candidates, adds a net 198 numerical RMP ratings and 428 GPA rows, and adds 107 verified teaching occurrences. Eight prior RMP matches returned to pending because additional department context exposed competing supported profiles. The prepared catalog now has 3,396 identified instructors, 1,411 numerical RMP ratings, and 12,238 verified GPA rows. There remain 444 ambiguous RMP cases, 6,386 unresolved GPA rows, and 17,261 unresolved subject/name labels; these labels are not unique people.

See the [batch results, source evidence and remaining priorities](coverage-expansion-2026-11-08.md) and [machine-readable review ledger](../data/mappings/coverage-expansion-review.json). Further review should prioritize historical LAS names, middle-name/nickname conflicts, and dated syllabi for specific teaching occurrences. No initials-only bulk expansion, Fall grade collection, or deployment was performed.

### Coverage review continuation

The second pass recovers another 520 GPA rows and 226 teaching occurrences, adds 20 supported RMP profiles (19 numerical ratings), and fully resolves two repeated subject/name labels. Current totals are 3,407 identified instructors, 1,430 numerical RMP ratings, 12,758 verified GPA rows, and 9,394 verified teaching occurrences. There remain 433 ambiguous RMP cases, 5,866 unresolved GPA rows, and 17,259 unresolved subject/name labels. This continuation withdrew no previous GPA or RMP matches.

The [continuation report](coverage-expansion-followup-2026-11-08.md) records the individually sourced professional-name reconciliations, public profile-URI identity evidence, reviewed legacy IHLT affiliation, and reuse of already-reviewed GPA source names for RMP matching. No global nickname/initial expansion, Fall grade collection, or deployment was performed.

## November 9, 2026: public deployment resumed

The user authorized resuming public deployment. Re-enable the Pages workflow and deploy the saved publication on `main` without a source refresh. The earlier deployment pauses above describe historical checkpoints; Fall grade collection remains outside scope.
