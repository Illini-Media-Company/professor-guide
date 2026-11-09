# Coverage review continuation — November 8, 2026

This continues the [first review](coverage-expansion-2026-11-08.md). All additions concern existing grade records, dated faculty evidence, and reviewed RMP matches. No Fall grades were collected and deployment remains paused.

## Results

| Coverage | Previous pass | Current | Added this pass |
| --- | ---: | ---: | ---: |
| Identified instructors | 3,396 | 3,407 | +11 |
| Verified RMP profiles | 1,587 | 1,607 | +20 |
| Numerical RMP ratings | 1,411 | 1,430 | +19 |
| Verified GPA rows | 12,238 | 12,758 | +520 |
| Verified teaching links | 9,168 | 9,394 | +226 |

Across both passes, numerical RMP coverage increased from 1,213 to 1,430, and verified GPA rows increased from 11,810 to 12,758. All prior grade links were retained. This continuation withdrew no previously accepted RMP matches. The eight competing-profile cases identified during the first pass remain pending.

## Grade recoveries

| Preserved source name | Additional grade rows |
| --- | ---: |
| Clarke, Caitlin L | 87 |
| Friedman, Roman | 60 |
| Licht, Mary J | 59 |
| Joesting, Jennifer J | 50 |
| Frasca, Elizabeth A | 37 |
| Colon, Carlos | 35 |
| Stoddard, Paul B | 23 |
| Alt, Amanda J | 21 |
| Mason, Terrence C | 21 |
| Taghaboni-Dutta, Fataneh | 21 |
| Raycraft, Michael | 20 |
| Wilson, Carrie A | 20 |
| Heuman, Joshua M | 19 |
| Mercer, Brian S | 19 |
| Golecki, Thomas F | 18 |
| DiFilippo, Kristen N | 7 |
| Lara-Cinisomo, Sandraluz | 2 |
| Mamaril, Cezar Brian C | 1 |

## Evidence used

- University personnel records supply full spellings for the individually reviewed Amanda/Mandi Alt, Caitlin Leeann/Caitlin Vitosky Clarke, Elizabeth Anne/Beth Frasca, Terrence C/Curtis Mason, and Thomas Farley/Tom Golecki cases. Public individual profiles and dated syllabi independently bind the professional name, university identity and teaching context. These are literal exceptions, not global nickname or middle-name expansion rules.
- The official CITL ASL contact list names Ivan Colon at colon17; the AHS directory supplies Carlos Ivan Colon at that same identity. The reviewed schedule spelling Colon, I can therefore be tied to the Carlos source name without guessing.
- Official LAS staff, university conference, and personnel sources identify Mary Jo/MJ Licht and Roman Friedman in the relevant LAS roles.
- The public Learn@Illinois course directory explicitly links Teacher Jennifer Joesting to a university teacher profile URI; a dated MCB faculty feature independently confirms her Anatomy & Physiology course-coordinator role. A namespaced profile-URI identity is used without inventing a NetID or accessing a protected profile.
- Dated individual Gies faculty-event/bio and course-feature pages establish Fataneh Taghaboni-Dutta and BADM 572/589 context even though a current directory entry is unavailable. This is historical faculty evidence, not a claim of current employment.
- The official HK subject notes and department program page identify IHLT as a former rubric/legacy program within Health and Kinesiology. Reviewed affiliation sources are fetched and attached to affected candidate evidence; if those sources are unavailable, only the added unit mapping is disabled. Course codes and grade samples stay separate.
- Seven reviewed published-name forms are stored in [the name-review ledger](../data/mappings/rmp-name-reviews.json), including Brad/Bradley Mehrtens, Matt/Matthew Winters, Alex/Alexander Vakakis, Ravi/Ravishankar Iyer, Max/Maxwell Fowler, Annie Ruth/Ann Abbott, and the explicitly printed full name Vimal Rao preceded by initials in V.N. Vimal Rao. Original display names remain unchanged.
- RMP matching can now reuse full names from existing, individually reviewed GPA bridges. Exact grade/name/source references and identity-review evidence are required; unreviewed grade names cannot contribute. Source-grade spelling provenance stays separate from the RMP metric retrieval source.
- An explicit parenthetical prefix nickname such as Timothy (Tim) is parsed as a nickname rather than a supplied middle name. Middle tokens outside parentheses are preserved, and an unexpanded nickname such as Tim alone is still not a full-name match.

## Remaining work

There are 433 ambiguous RMP cases, 5,866 unassigned GPA rows, and 17,259 unresolved subject/name labels. These labels are not counts of distinct people. The current queues remain in the [identity report](identity-review-coverage.md) and [RMP audit](rmp-coverage.md).

Two subject/name labels became fully resolved; most new teaching links only resolve particular course/term occurrences within repeated labels. Remaining examples include Matthew Hutchens, where multiple ACCY instructors share the initial M; Nicholas Handy rows without matching archived course/term occurrences; and Emily Hurth, whose individual official identity/contact evidence still needs review. Sources that returned unavailable pages or access denial were not treated as proof of absence.

The [follow-up ledger](../data/mappings/coverage-expansion-followup.json) lists every recovered grade ID, new RMP match and new occurrence link. The normalized inputs and local visitor bundle have been rebuilt using saved source data.


## Validation and delivery

All 154 data tests, 10 UI model tests and 19 browser checks pass, along with the production build and publication hash/join validation. The final local bundle retains the original main publication objects alongside the new candidate (44 objects, 241.8 MiB). The changes are on `improve/coverage-review`. Pushing this branch does not merge it into main or resume deployment; Pages remains manually disabled.
