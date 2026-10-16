"""Validate the published manifest, archive objects, and teammate joins offline."""

import argparse
import json
from pathlib import Path
import sys

from scripts.data_contract import DataError, require, validate_document
from scripts.integration import validate_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Validate one isolated collection candidate instead')
    args = parser.parse_args()
    try:
        if args.input:
            validate_document(json.loads(args.input.read_text(encoding='utf-8')))
            print(f'Valid candidate: {args.input}')
        else:
            manifest, files = validate_bundle('public/data')
            require(manifest['data_kind'] == 'live', 'Fixtures cannot be deployed as visitor data')
            require(sorted(path.name for path in Path('public/data').glob('*.json')) == ['integration.json'],
                    'Publish through the manifest; remove unvalidated or retired fixed-name exports')
            objects = list(Path('public/data/objects').glob('*.json'))
            require(all(item.stat().st_size < 95 * 1024 * 1024 for item in objects), 'Public object exceeds GitHub file budget')
            size = sum(item.stat().st_size for item in objects)
            require(size < 900 * 1024 * 1024, 'Public data exceeds the GitHub Pages size budget')
            print(f'Valid live publication: {manifest["coverage"]["section_count"]:,} current sections')
            totals = files['history']['coverage']['totals']
            print(f'Archive: {totals["collected_terms"]} terms, {totals["course_count"]:,} listings, {totals["section_count"]:,} sections')
            print(f'All hashes/joins validated; {len(objects)} retained objects, {size / 1024 / 1024:.1f} MiB')
    except (DataError, ValueError, OSError, KeyError) as error:
        print(f'Validation failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
