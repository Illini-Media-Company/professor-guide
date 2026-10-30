# Synthetic GPA importer fixture

`tiny-synthetic.csv` is invented development data, not a real observation.
Its columns follow Wade's documented GPA CSV format. Never publish it as live data.
`windows1252-synthetic.csv` is also invented; it contains an accented name
encoded as Windows-1252 to exercise strict, explicit decoding.

Preview without writing files, from the repository root:

```sh
python -m scripts.import_gpa data/examples/gpa/tiny-synthetic.csv --synthetic
```

The preview marks its validation envelope `data_kind: "development_fixture"`.
Processing details retain original CSV cell values, grade counts, W, source
Students, file SHA-256, and one-based data-record position separately from
the existing normalized GPA contract. Blank count cells mean unavailable;
other non-integer tokens are errors. Blank instructors remain in processing
for review and have no normalized record. Rows are never combined or removed
as duplicates. IDs are deterministic within a source-file snapshot; changing
any source-file bytes changes its hash and row IDs. No network or publication
is performed.

## Encoding and unpublished real-source candidates

The API is `import_csv(path, encoding="utf-8-sig")`. UTF-8 (with optional BOM)
is the default. Decoding is strict: there is no fallback, ignored byte, or
replacement character. `--encoding cp1252` is an explicit interpretation,
not verification that an upstream source declared Windows-1252. Hashes and
row IDs always use the original file bytes; selected encoding and byte size
are recorded in processing metadata.

```sh
python -m scripts.import_gpa data/examples/gpa/windows1252-synthetic.csv --synthetic --encoding cp1252 --summary
python -m scripts.import_gpa LOCAL_SNAPSHOT.csv --encoding cp1252 --source-url https://example.org/actual-source.csv --fetched-at ACTUAL_FETCH_TIMESTAMP --summary
```

The second command is a template: supply the actual source URL and recorded
timezone-aware fetch timestamp. It validates a `data_kind: "live"` candidate
with the existing GPA validator, without publishing or writing any files.
`--synthetic` cannot be combined with real provenance. API callers can use
`candidate_envelope(records, source_url=..., fetched_at=...)`; it has no
fixture defaults. Without `--summary`, stdout includes detailed processing
and the separate normalized envelope. Use ignored local storage for any
saved real-data artifacts, never `data/inputs/` or `public/data/` at this stage.
The explicit saved-export mode below is the exception for `data/inputs/gpa.json`;
it is still not publication.

Every successfully parsed row remains in processing. `missing_primary_instructor`
and `course_code_outside_contract` are explicit normalized-export exclusions;
course numbers are never padded. Missing grade counts are review warnings
and permit normalized null GPA/student_count. Malformed counts, inconsistent
Students totals, invalid terms, and broken CSV structure remain errors.

Accounting reports parsed rows, eligible normalized rows, unique ineligible
rows, exclusion reason counts, and all review reason counts. Multiple reasons
can apply to one row, so reason counts can exceed the ineligible-row count.
The importer checks that eligible + ineligible equals parsed. Validation of
a candidate does not establish archive coverage or authorize publication.

## Compatible saved export

Run from the repository root with the unchanged locally retained snapshot.
No fetching, collector, publisher, or professor matching is invoked:

```powershell
& 'C:\Users\eghan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m scripts.import_gpa data/raw/wade-gpa/20261030T211543172904Z/uiuc-gpa-dataset.csv --encoding cp1252 --provenance data/raw/wade-gpa/20261030T211543172904Z/provenance.json --export --output data/inputs/gpa.json --artifacts-dir data/reports/gpa --config config/collection.json --public-dir public/data --summary
```

This snapshot's original byte SHA-256 is
`7e00a38b6c05c3989342a6580f95965f903e753c66687d5b7d3ed0764080f855`;
its size is 11,806,363 bytes. The recorded source is
`https://raw.githubusercontent.com/wadefagen/datasets/main/gpa/uiuc-gpa-dataset.csv`,
fetched at `2026-10-30T21:15:43.172904Z`. The exporter checks hash and size
against `provenance.json`, and uses its actual URL/timestamp in the envelope.
`collected_at` is the fetch time, not the export execution time.

Saved history is resolved through `public/data/integration.json` with the
existing hash/size validator. Its start/end/requested terms must agree with
configuration and the manifest's current term, or export stops. The filter
mirrors `update_data`: membership in **requested terms**, including any
confirmed-unavailable terms; it does not require collected-term membership.
Current configuration allows Winter 2023 through Fall 2026. This snapshot
has eligible rows through Summer 2026. Source/contract exclusions remain
separate from otherwise-eligible rows outside that requested range.

`--artifacts-dir data/reports/gpa` creates a fresh UTC-named run directory in
ignored local storage. The printed report path identifies `export-report.json`;
its sibling `processing.jsonl` contains every parsed source record, one JSON
object per line, including exclusion outcomes and original values. The report
records complete row accounting, per-term export/coverage exclusions,
source provenance/encoding, configuration and manifest hashes, the referenced
history object, output hash/size, and export execution time. Keep these files
with the raw snapshot and provenance to reproduce or audit an export.

For identical inputs the envelope bytes are deterministic; execution timestamps
and audit-directory names vary. An existing equal GPA input is left untouched.
A changed existing input stops export for approval; no overwrite option exists.
Every complete envelope is validated with the existing GPA validator before
writing. Synthetic previews still use `--synthetic` and fixture metadata;
real exports require recorded provenance and never substitute fixture values.

Results remain **per-source-row averages**, not pooled course averages.
Professor attribution remains a separate evidence-backed verified-link
operation. No aggregation or publication is performed by this command.
