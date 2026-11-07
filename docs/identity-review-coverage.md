# Identity review coverage

Review run: `2026-11-02T16:07:11Z`.

All **3,921 GPA source-name labels** and **18,624 grade rows** were evaluated against the saved official directory sources and the campus archive.
**2,287 distinct directory identities** have supporting full-name and department evidence. 11,810 grade rows have a reviewed course/term occurrence; 6,814 require further evidence.

Names with incomplete, conflicting, or unavailable evidence stay unresolved. Public source access failures are recorded in the ledger. Current rosters may omit former instructors.

## GPA outcomes

| Grade-row outcome | Rows |
| --- | ---: |
| no_full_name_and_department_match | 6,106 |
| department_not_verified_for_this_subject | 312 |
| no_matching_schedule_occurrence | 209 |
| ambiguous_grade_source_names | 89 |
| ambiguous_schedule_initials | 80 |
| multiple_official_identities | 18 |

## Archive source-name outcomes

Each row is a subject/name label; abbreviated labels are not counts of unique people. Grade-backed reviews are retained separately from unverified historical occurrences.
13,280 labels have no matching GPA surname/initial in that subject. The other 4,072 have possible GPA context; initials alone do not verify a shared identity.

| Outcome | Subject/name labels |
| --- | ---: |
| needs_additional_source_evidence | 12,302 |
| candidate_requires_occurrence_review | 2,631 |
| partially_verified_occurrences | 2,281 |
| verified_occurrences | 91 |
| ambiguous_directory_identities | 47 |

## Follow-up queue

| GPA source name | Rows | Subjects | Reason |
| --- | ---: | --- | --- |
| Miller, Thomas J | 103 | THEA | no_full_name_and_department_match |
| Clarke, Caitlin L | 87 | CHLH, HK, KIN | no_full_name_and_department_match |
| Soranso, Murillo S | 87 | ENG | no_full_name_and_department_match |
| Powers, Kimberly | 81 | ENG | no_full_name_and_department_match |
| Friedman, Roman | 60 | LAS | no_full_name_and_department_match |
| Licht, Mary J | 59 | LAS | no_full_name_and_department_match |
| Joesting, Jennifer J | 50 | MCB | no_full_name_and_department_match |
| Clegg, Benjamin F | 47 | IB | no_full_name_and_department_match |
| Augusto Sampaio, Gerlando | 41 | ACCY | no_full_name_and_department_match |
| Gundersen, Lisa C | 39 | ACE | no_full_name_and_department_match |
| Frasca, Elizabeth A | 37 | CHLH, HK, IHLT | no_full_name_and_department_match |
| Gist, Toni M | 30 | FSHN | no_full_name_and_department_match |
| Stoddard, Paul B | 23 | ACE | no_full_name_and_department_match |
| Alt, Amanda J | 21 | ACCY | no_full_name_and_department_match |
| Mason, Terrence C | 21 | EDUC, EPOL | no_full_name_and_department_match |
| Taghaboni-Dutta, Fataneh | 21 | BADM | no_full_name_and_department_match |
| Raycraft, Michael | 20 | RST | no_full_name_and_department_match |
| Wilson, Carrie A | 20 | ADV, MACS | no_full_name_and_department_match |
| Brobst, Charles | 19 | FIN | no_full_name_and_department_match |
| Heuman, Joshua M | 19 | JOUR, MACS | no_full_name_and_department_match |
| Mercer, Brian S | 19 | ME, TAM | no_full_name_and_department_match |
| Werkheiser, Amy R | 19 | REL | no_full_name_and_department_match |
| Golecki, Thomas F | 18 | ME, TAM | no_full_name_and_department_match |
| Hurth, Emily S | 18 | HDFS | no_full_name_and_department_match |
| Kim, Heejin | 18 | BUS, LING | multiple_official_identities |
| Woodson, Markisha J | 18 | CHLH, HK | no_full_name_and_department_match |
| Fisher, Mitchell B | 17 | ACCY | no_full_name_and_department_match |
| Manouchehri Ira, Rustom D | 17 | FIN | no_full_name_and_department_match |
| Titone, Thomas A | 17 | SE | no_full_name_and_department_match |
| Icaza, Eric S | 16 | ASRM, STAT | no_full_name_and_department_match |

The complete [GPA queue](../data/mappings/identity-review.csv) includes every source label. The [archive queue](../data/mappings/archive-identity-review.csv) includes every subject/name pair. The [review ledger](../data/mappings/professor-identities.json) records row-level decisions, directory IDs, source URLs/hashes/timestamps, and input fingerprints.

Reproduce with saved source responses: `python3 -m scripts.review_identities --reuse-sources --include-archive`. Use `--apply` to export accepted evidence-backed decisions to normalized inputs. These commands do not publish or deploy.
