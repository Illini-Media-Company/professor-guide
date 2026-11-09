# Normalized publication inputs

These committed files supply real enrichment data to `scripts.update_data`:

| File | Dataset |
| --- | --- |
| `gpa.json` | Normalized source GPA rows, grade grain, enrollment counts, provenance |
| `professors.json` | Verified instructor identities, faculty links, professor-wide RMP summaries |
| `verified-links.json` | Reviewed schedule occurrences and individual grade-name bridges |

Paths are configured in `config/collection.json`. See the [data contract](../../docs/data-contract.md), [review workflow](../mappings/README.md), and [synthetic shape examples](../examples/integration/README.md). Raw downloads belong in ignored `data/raw/` or `data/downloads/`. Production rejects synthetic inputs.

After reviewed input changes, run `python -m scripts.update_data --reuse-current` and `npm run validate:data`. This rebuilds the publication from saved schedules without source requests; it does not deploy until pushed to main.
