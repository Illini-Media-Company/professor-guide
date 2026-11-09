# Identity review coverage

Review run: `2026-11-08T22:44:24Z`.

All **3,921 GPA source-name labels** and **18,624 grade rows** were evaluated against the saved official directory sources and the campus archive.
**2,308 distinct directory identities** have supporting full-name and department evidence. 12,758 grade rows have a reviewed course/term occurrence; 5,866 require further evidence.

Names with incomplete, conflicting, or unavailable evidence stay unresolved. Public source access failures are recorded in the ledger. Current rosters may omit former instructors.

## GPA outcomes

| Grade-row outcome | Rows |
| --- | ---: |
| no_full_name_and_department_match | 5,203 |
| department_not_verified_for_this_subject | 302 |
| no_matching_schedule_occurrence | 174 |
| ambiguous_grade_source_names | 89 |
| ambiguous_schedule_initials | 80 |
| multiple_official_identities | 18 |

## Archive source-name outcomes

Each row is a subject/name label; abbreviated labels are not counts of unique people. Grade-backed reviews are retained separately from unverified historical occurrences.
13,272 labels have no matching GPA surname/initial in that subject. The other 4,080 have possible GPA context; initials alone do not verify a shared identity.

| Outcome | Subject/name labels |
| --- | ---: |
| needs_additional_source_evidence | 12,277 |
| candidate_requires_occurrence_review | 2,620 |
| partially_verified_occurrences | 2,315 |
| verified_occurrences | 93 |
| ambiguous_directory_identities | 47 |

## Follow-up queue

| GPA source name | Rows | Subjects | Reason |
| --- | ---: | --- | --- |
| Brobst, Charles | 19 | FIN | no_full_name_and_department_match |
| Werkheiser, Amy R | 19 | REL | no_full_name_and_department_match |
| Hurth, Emily S | 18 | HDFS | no_full_name_and_department_match |
| Kim, Heejin | 18 | BUS, LING | multiple_official_identities |
| Woodson, Markisha J | 18 | CHLH, HK | no_full_name_and_department_match |
| Fisher, Mitchell B | 17 | ACCY | no_full_name_and_department_match |
| Manouchehri Ira, Rustom D | 17 | FIN | no_full_name_and_department_match |
| Titone, Thomas A | 17 | SE | no_full_name_and_department_match |
| Icaza, Eric S | 16 | ASRM, STAT | no_full_name_and_department_match |
| Mitchell, Elissa T | 16 | HDFS | no_full_name_and_department_match |
| Sanchez, Donovan | 16 | ACE | no_full_name_and_department_match |
| Wroblewski, Gabrielle E | 16 | AE | no_full_name_and_department_match |
| Burnett, Meghan L | 15 | ACE | no_full_name_and_department_match |
| Gunasekera, Mutha Merenna | 15 | CHEM | no_full_name_and_department_match |
| Johnson, Jennifer A | 15 | ACCY | no_full_name_and_department_match |
| Niu, Mukun | 15 | ECON | no_full_name_and_department_match |
| Rahman, Nisa P | 15 | ADV | no_full_name_and_department_match |
| Tang, Chenxi | 15 | ECON | no_full_name_and_department_match |
| Warnick, Emerson T | 15 | BADM | no_full_name_and_department_match |
| Ansell, Katherine A | 14 | PHYS | no_full_name_and_department_match |
| Aviram, Amitai | 14 | LAW | no_full_name_and_department_match |
| Font Bas, Victor | 14 | MACS | no_full_name_and_department_match |
| Raveendran Nair, Gopu | 14 | ETMA | no_full_name_and_department_match |
| Schrag, David M | 14 | GLBL | no_full_name_and_department_match |
| Zhao, Zixuan | 14 | ADV, MACS | no_full_name_and_department_match |
| Adohinzin, Wilfried Doria | 13 | ECON | no_full_name_and_department_match |
| Amos, Jennifer | 13 | BIOE, ENG | no_full_name_and_department_match |
| Barich, Joseph M | 13 | SE, TE | no_full_name_and_department_match |
| Brockett, Josie A | 13 | ALEC, LEAD | no_full_name_and_department_match |
| Corredor Waldro, Sandra T | 13 | BADM, BUS | no_full_name_and_department_match |

The complete [GPA queue](../data/mappings/identity-review.csv) includes every source label. The [archive queue](../data/mappings/archive-identity-review.csv) includes every subject/name pair. The [review ledger](../data/mappings/professor-identities.json) records row-level decisions, directory IDs, source URLs/hashes/timestamps, and input fingerprints.

Reproduce with saved source responses: `python3 -m scripts.review_identities --reuse-sources --include-archive`. Use `--apply` to export accepted evidence-backed decisions to normalized inputs. These commands do not publish or deploy.
