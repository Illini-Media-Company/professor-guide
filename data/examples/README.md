# Synthetic development fixtures

Every XML file in `course-explorer-xml/` and the generated `course-explorer.json` is synthetic. CRNs, people, schedules, titles, and the January collection timestamp are invented. The XML hierarchy follows the inspected official responses; edge cases are deliberately added. These files are not a live schedule or verified professor matches.

The fixture has two related listings and four registration sections. CS includes a lecture with two instructors, a second laboratory meeting with a different instructor, a discussion with an empty instructor container, and a laboratory with an absent instructor container. ECE keeps its own lecture CRN even though its meeting resembles the CS lecture. Explicit “Same as” / “See” text supplies alias evidence.

Tests parse these XML fixtures without network access. `course-explorer.json` is a complete frontend handoff example labeled `data_kind: "development_fixture"`. Publishing it requires an explicit `--allow-fixtures` flag, and the interface displays a synthetic-data label.

`discovery-xml/` contains additional synthetic calendar/year/term/subject indexes. They intentionally list only Fall 2026 and Spring 2025, and only CS/ECE 374, to exercise missing terms, subjects, and courses. They are not copied live availability indexes. Tests reuse the small course fixtures across those terms while keeping term-qualified IDs distinct. Teaching-history bundle fixtures are assembled in memory and labeled `development_fixture`; the public history file contains live records.
