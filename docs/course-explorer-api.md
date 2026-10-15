# Verified Course Explorer observations

Verified October 14, 2026, America/Chicago, with HTTPS certificate verification enabled. Source fetch timestamps are saved in UTC (the initial live snapshot is dated October 15 in UTC).

## Official endpoints inspected

- [2026 term index](https://courses.illinois.edu/cisapp/explorer/schedule/2026.xml) returned Winter, Spring, Summer, and Fall. Fall's official term ID was `120268`.
- [Fall 2026 CS 374 index](https://courses.illinois.edu/cisapp/explorer/schedule/2026/fall/CS/374.xml) returned 20 section references.
- [Fall 2026 CS 374 detail](https://courses.illinois.edu/cisapp/explorer/schedule/2026/fall/CS/374.xml?mode=detail) returned those 20 complete sections.
- [Fall 2026 ECE 374 index](https://courses.illinois.edu/cisapp/explorer/schedule/2026/fall/ECE/374.xml) and [detail](https://courses.illinois.edu/cisapp/explorer/schedule/2026/fall/ECE/374.xml?mode=detail) returned 21 separate registration sections.
- [CS lecture AL1 / CRN 66445](https://courses.illinois.edu/cisapp/explorer/schedule/2026/fall/CS/374/66445.xml) and [discussion ADA / CRN 70643](https://courses.illinois.edu/cisapp/explorer/schedule/2026/fall/CS/374/70643.xml) were inspected individually.

## Actual XML shape

The root was `ns2:course` with namespace `http://rest.cis.illinois.edu`; the children were unprefixed. The parser normalizes namespaces rather than assuming every child shares the root namespace.

The ordinary course XML included:

```xml
<ns2:course id="CS 374" href="…" xmlns:ns2="http://rest.cis.illinois.edu">
  <parents>
    <calendarYear id="2026" href="…">2026</calendarYear>
    <term id="120268" href="…/2026/fall.xml">Fall 2026</term>
    <subject id="CS" href="…">Computer Science</subject>
  </parents>
  <label>…</label>
  <description>…</description>
  <courseSectionInformation>…</courseSectionInformation>
  <sections><section id="66445" href="…/66445.xml">AL1</section></sections>
</ns2:course>
```

The detailed course XML used `detailedSections/detailedSection` instead of `sections/section`. Each detailed section included its own `parents`, `sectionNumber`, and `meetings/meeting`. The individual section endpoint used the same children inside an `ns2:section` root. The collector uses the detailed course endpoint plus the separate ordinary index to limit requests while checking completeness.

Meetings included `start`, `end`, `daysOfTheWeek`, `roomNumber`, `buildingName`, `type`, and `instructors/instructor`. `type` had a `code` attribute (`LEC` or `DIS` in this sample). Each instructor had visible text and `firstName` / `lastName` attributes. The sample used initials in the first-name field; that is insufficient for a verified professor match.

The original Fall 2026 two-course sample contained 41 meetings: five lectures and 36 discussions. Every meeting listed one instructor. The synthetic fixtures extended that initial sample to cover labs, multiple meetings/instructors, and empty/absent instructor containers. The expanded pilot below now verifies some of those cases live.

CS 374 explicitly named ECE 374 in “Same as” text; ECE 374 explicitly named CS 374 in both “Same as” and “See” text. Both `description` and `courseSectionInformation` carried that evidence. The collector retains those fields and source locations in the generated relationship records. CS and ECE CRNs remain separate.

## Limits of verification

The legacy [API documentation URL](https://courses.illinois.edu/cisdocs/api) and `/cisdocs/explorer` returned HTTP 302 redirects to the Course Explorer homepage using the system HTTP client. The web browsing service could not retrieve those pages either. A current published API specification, request quotas/rate limits, supported query-mode guarantees, pagination guarantees, and uptime commitments could not be verified.

`?mode=detail` and the XML hierarchy were verified directly for these two courses. No general completeness guarantee is assumed: the collector compares index and detail CRNs and fails closed on missing sections or meetings. Timeouts, retries, and rate-limit failures are tested with local mocks; an actual upstream outage or HTTP 429 was not induced. The implementation applies a small bounded request policy and uses cached successful responses, with a weekly scheduled refresh in GitHub Actions (see [operations](operations.md)).

## Expanded teaching-history pilot

The next milestone was verified live on October 14, 2026, Central time. The [root calendar index](https://courses.illinois.edu/cisapp/explorer/schedule.xml) listed years 2004 through 2027. The [2025 index](https://courses.illinois.edu/cisapp/explorer/schedule/2025.xml) and [2026 index](https://courses.illinois.edu/cisapp/explorer/schedule/2026.xml) each listed Winter, Spring, Summer, and Fall. Requested Spring 2025 used official ID `120251`; Fall 2026 used `120268`.

The [Fall 2026 subject index](https://courses.illinois.edu/cisapp/explorer/schedule/2026/fall.xml) and [Spring 2025 subject index](https://courses.illinois.edu/cisapp/explorer/schedule/2025/spring.xml), followed by each CS/ECE/STAT/IS subject index, confirmed all five requested listings in both terms. Both course index and detail XML returned HTTP 200 for all ten combinations. The [history coverage report](integration-history-coverage.md) shows exact counts; `public/data/teaching-history.json` retains all 33 successful discovery/course source URLs and fetch times.

The expanded sample contains 308 registration sections and 310 meetings. Thirty-three meetings list multiple instructors. The source labels include `LBD` (Laboratory-Discussion) and `OLC` (Online Lecture), in addition to `LEC` and `DIS`. Spring 2025 CS 374 and ECE 374 each contain a section with an extra meeting; its instructors remain on that meeting. All 343 instructor occurrences remain unresolved. No empty or absent instructor lists occurred in this live pilot; those remain fixture-covered cases, as do standalone `LAB` roles.

The 107 listings explicitly supply compound “Same as” evidence for CS 107, IS 107, and STAT 107. Each listing and CRN is preserved separately. No times, room numbers, or shared instructor names are used to infer section linkage or professor identities.

A small availability probe also checked valid indexes with deliberately unlisted requests: CS 999 was absent from the Fall 2026 CS index, and 2099 was absent from the root year index. They were reported as `course_not_listed` and `year_not_listed` without requesting guessed child endpoints. This probe is separate from the pilot and does not change its requested coverage.

## Campus batch verification

The full milestone live-verified `AAS.xml?mode=cascade` and `CS.xml?mode=cascade`, then a mixed AAS/CS/MATH/CHEM/MUS sample, then all 186 discovered Fall 2026 departments. The response root is `subject`, containing `cascadingCourses/cascadingCourse/detailedSections/detailedSection`. `?mode=detail` at department level did not provide nested sections. The implemented collector therefore uses the verified cascade mode and separately checks its course set against the ordinary subject index.

Campus coverage: 4,452 listings, 12,839 registration sections, 13,640 meetings, 18,594 listed instructor occurrences, 534 meetings without instructors, 3,906 meetings with multiple instructors, and 426 sections without a source label. All identities remain unresolved. Codes such as Independent Study, Packaged Section, and specialty clinical roles are retained without being forced into lecture/lab/discussion categories. Actual response URLs and source timestamps are recorded separately from canonical individual course/section URLs. See `current-coverage.md` for every department.

No rate-limit or access restriction was bypassed. HTTPS verification and 0.4-second minimum pacing were used. HTTP 401/403 causes an immediate stop. Missing section labels were inspected in actual CS 397/497/499/597 XML before adding explicit missing-label support. No zero-section courses or zero-meeting sections occurred in this campus snapshot.

Salary Guide was inspected at `42a41bc09bf1cb2883ea044b6436fc34e13916d4`; its React/Vite, repository base path, and saved-JSON patterns informed the starter.
