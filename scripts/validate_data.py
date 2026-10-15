"""Check a saved Course Explorer snapshot without network access or file changes."""

import argparse
import json
from pathlib import Path
import sys

from scripts.data_contract import DataError, validate_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Default: validate both public datasets, when history exists")
    args = parser.parse_args()
    try:
        inputs = [args.input] if args.input else [Path("public/data/course-explorer.json")]
        if args.input is None and Path("public/data/teaching-history.json").exists():
            inputs.append(Path("public/data/teaching-history.json"))
        for input_path in inputs:
            snapshot = validate_document(json.loads(input_path.read_text(encoding="utf-8")))
            if snapshot["dataset"] == "teaching_history":
                totals = snapshot["coverage"]["totals"]
                print(f'Valid {snapshot["data_kind"]} history: {totals["collected_course_terms"]} course/term pairs, {totals["section_count"]} sections')
            else:
                print(f'Valid {snapshot["data_kind"]} snapshot: {len(snapshot["courses"])} listings, {len(snapshot["sections"])} sections')
        if args.input is None and Path("public/data/integration.json").exists():
            from scripts.integration import validate_bundle
            manifest, _ = validate_bundle("public/data")
            print(f'Valid integration manifest and all file hashes: {manifest["coverage"]["section_count"]} current sections')
    except (DataError, ValueError, OSError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
