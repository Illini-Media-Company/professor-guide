# Generated visitor data

`course-explorer.json` is the validated, saved Course Explorer snapshot served to visitors. It contains live Fall 2026 CS 374 and ECE 374 records and unresolved instructor identities. Its `sources` entries and UTC timestamps identify the actual source fetches.

Generate it with `python3 -m scripts.publish_data --input data/snapshots/course-explorer-2026-fall.json` after collecting and reviewing a candidate. Do not hand-edit generated JSON. Commit reviewed changes so GitHub Pages builds remain independent of the upstream API.

`teaching-history.json` is the additive live Fall 2026 / Spring 2025 pilot for CS/ECE 374 and CS/STAT/IS 107. It contains two unchanged v1 Course Explorer snapshots plus discovery provenance and coverage for every requested pair. It is the handoff dataset for GPA processing and professor matching; identities are unresolved. See [the consumption guide](../../docs/teaching-history.md) and [coverage report](../../docs/pilot-coverage.md).

Publish history with `python3 -m scripts.publish_data --input data/snapshots/teaching-history.json`. The publisher chooses the corresponding public filename and does not replace the frontend's original snapshot. `npm run validate:data` validates both files when history is present. Each dataset is a self-contained atomic replacement; builds never fetch live data.

GPA and professor/RMP files will be added after their owners agree on contracts and supply validated outputs. The current publisher supports only Course Explorer snapshots and the teaching-history bundle.

The full integration entry point is now `integration.json`. Its immutable `objects/<sha256>.json` files contain the complete current campus schedule, durable history, aliases, department coverage, and preview. Grade/professor/link inputs are explicitly pending until supplied. Do not rename objects or edit a manifest/hash by hand. Run `python -m scripts.update_data` for coordinated publication and `npm run validate:data` to check every referenced object. The old demo files remain compatible.
