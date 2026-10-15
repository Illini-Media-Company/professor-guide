"""Validate one collected snapshot and atomically publish it for the static frontend."""

import argparse
import json
from pathlib import Path
import sys

from scripts.data_contract import DataError, atomic_write_json, require, validate_document

ROOT = Path(__file__).resolve().parents[1]


def publish(input_path, output_path=None, allow_fixtures=False):
    snapshot = validate_document(json.loads(Path(input_path).read_text(encoding="utf-8")))
    require(allow_fixtures or snapshot["data_kind"] == "live", "Fixture publication requires --allow-fixtures")
    expected_name = "teaching-history.json" if snapshot["dataset"] == "teaching_history" else "course-explorer.json"
    output_path = Path(output_path) if output_path is not None else ROOT / "public/data" / expected_name
    if output_path.resolve().is_relative_to((ROOT / "public").resolve()):
        require(output_path.name == expected_name, "Public filename must match the dataset; preserve the existing frontend contract")
    # Preserve source timestamps exactly; publishing is not collection.
    atomic_write_json(output_path, snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Default public filename is selected by dataset")
    parser.add_argument("--allow-fixtures", action="store_true", help="Explicitly publish labeled development data")
    args = parser.parse_args()
    try:
        snapshot = publish(args.input, args.output, args.allow_fixtures)
    except (DataError, OSError, ValueError) as error:
        print(f"Publication failed; existing published snapshot preserved: {error}", file=sys.stderr)
        return 1
    target = args.output or ROOT / "public/data" / ("teaching-history.json" if snapshot["dataset"] == "teaching_history" else "course-explorer.json")
    print(f'Published {snapshot["data_kind"]} {snapshot["dataset"]} data → {target} (collected {snapshot["collected_at"]})')
    return 0


if __name__ == "__main__":
    sys.exit(main())
