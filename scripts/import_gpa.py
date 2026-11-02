"""Parse local Wade GPA CSV rows without aggregation or publication.

Counts are integers; grade points are represented in hundredths to avoid
rounding intermediate calculations. Only the final normalized GPA is a float.
The CLI previews candidates or explicitly exports a range-filtered input
and local audit artifacts; it never publishes. An explicit encoding is a decoding choice,
not a claim that the source declared that encoding.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from scripts.data_contract import COURSE_PATTERN, DataError, parse_term_id, require
from scripts.archive import requested_terms
from scripts.integration import encoded, read, read_object, validate_input


# Illinois grade points multiplied by 100, in documented CSV column order.
GRADE_POINTS = dict(zip(
    ('A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F'),
    (400, 400, 367, 333, 300, 267, 233, 200, 167, 133, 100, 67, 0),
))
COLUMNS = ('Year', 'Term', 'YearTerm', 'Subject', 'Number', 'Course Title',
           'Sched Type', *GRADE_POINTS, 'W', 'Students', 'Primary Instructor')


def count_value(value, column):
    """Only blank cells mean missing; malformed counts are errors."""
    value = value.strip()
    if not value:
        return None
    require(re.fullmatch(r'[0-9]+', value) is not None,
            f'{column} must be a nonnegative integer or blank')
    return int(value)


def parse_row(raw, source_hash, position):
    year, season = raw['Year'].strip(), raw['Term'].strip().lower()
    term_id = f'{year}-{season}'
    parse_term_id(term_id)
    course_code = f"{raw['Subject'].strip().upper()} {raw['Number'].strip().upper()}"
    counts = {grade: count_value(raw[grade], grade) for grade in GRADE_POINTS}
    withdrawals = count_value(raw['W'], 'W')
    source_students = count_value(raw['Students'], 'Students')
    complete = all(count is not None for count in counts.values())
    student_count = sum(counts.values()) if complete else None
    numerator = sum(counts[grade] * points for grade, points in GRADE_POINTS.items()) if complete else None
    if complete and source_students is not None:
        require(source_students == student_count, 'Students disagrees with A-F count')
    gpa = float(Fraction(numerator, 100 * student_count)) if student_count else None
    name = raw['Primary Instructor'].strip()
    reasons = []
    exclusions = []
    if not complete:
        reasons.append('missing_letter_grade_counts')
    if not name:
        exclusions.append('missing_primary_instructor')
    if COURSE_PATTERN.fullmatch(course_code) is None:
        exclusions.append('course_code_outside_contract')
    reasons.extend(exclusions)
    identifier = f'{source_hash}:row-{position}'
    processing = {
        'id': identifier, 'source_file_sha256': source_hash,
        'source_record_position': position, 'original': dict(raw),
        'term_id': term_id, 'course_code': course_code,
        'grade_counts': counts, 'withdrawals': withdrawals,
        'source_students': source_students, 'student_count': student_count,
        'weighted_total_hundredths': numerator, 'gpa': gpa,
        'review_reasons': reasons, 'exclusion_reasons': exclusions,
        'normalized_eligible': not exclusions,
    }
    normalized = None if exclusions else {
        'id': identifier, 'term_id': term_id, 'course_code': course_code,
        'grain': 'instructor_course_term', 'section_id': None,
        'primary_instructor_name_raw': name, 'gpa': gpa,
        'student_count': student_count,
    }
    return processing, normalized


def import_csv(path, encoding='utf-8-sig'):
    """Return separate processing and eligible records; never write files.

    Positions are one-based CSV data-record numbers, excluding the header,
    rather than physical line numbers (quoted cells may contain newlines).
    IDs identify rows within this exact source-file snapshot.
    """
    body = Path(path).read_bytes()
    source_hash = hashlib.sha256(body).hexdigest()
    processing, normalized = [], []
    reader = csv.DictReader(io.StringIO(body.decode(encoding, errors='strict'), newline=''), strict=True)
    try:
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(COLUMNS)
                and set(reader.fieldnames) == set(COLUMNS), 'Unexpected GPA CSV columns')
        for position, raw in enumerate(reader, 1):
            require(None not in raw and all(value is not None for value in raw.values()),
                    f'Record {position}: wrong number of CSV cells')
            try:
                detail, record = parse_row(raw, source_hash, position)
            except DataError as error:
                raise DataError(f'Record {position}: {error}') from error
            processing.append(detail)
            if record is not None:
                normalized.append(record)
    except csv.Error as error:
        raise DataError(f'Malformed CSV: {error}') from error
    excluded = sum(not detail['normalized_eligible'] for detail in processing)
    require(len(normalized) + excluded == len(processing), 'GPA row accounting mismatch')
    accounting = {
        'parsed_rows': len(processing), 'eligible_normalized_rows': len(normalized),
        'ineligible_rows': excluded,
        'exclusion_reason_counts': dict(Counter(reason for detail in processing
                                               for reason in detail['exclusion_reasons'])),
        'review_reason_counts': dict(Counter(reason for detail in processing
                                            for reason in detail['review_reasons'])),
    }
    return {'source_file_sha256': source_hash, 'source_bytes': len(body),
            'encoding': encoding, 'accounting': accounting,
            'observed_terms': sorted({detail['term_id'] for detail in processing},
                                    key=lambda term: (int(term.split('-')[0]),
                                                      ('winter', 'spring', 'summer', 'fall').index(term.split('-')[1]))),
            'processing_records': processing, 'normalized_records': normalized}


def candidate_envelope(records, *, source_url, fetched_at):
    """Validate an unpublished live candidate using caller-supplied provenance."""
    url = urlsplit(source_url)
    require(url.scheme == 'https' and bool(url.hostname), 'Source URL must be HTTPS with a host')
    return validate_input({
        'schema_version': 1, 'dataset': 'gpa', 'data_kind': 'live',
        'collected_at': fetched_at,
        'sources': [{'url': source_url, 'fetched_at': fetched_at}],
        'records': records,
    }, 'gpa')


def synthetic_envelope(records):
    """Fixture-only validation envelope; timestamps are synthetic, not fetches."""
    return validate_input({
        'schema_version': 1, 'dataset': 'gpa', 'data_kind': 'development_fixture',
        'collected_at': '2026-01-01T00:00:00Z',
        'sources': [{'url': 'https://example.org/synthetic-gpa-fixture',
                     'fetched_at': '2026-01-01T00:00:00Z'}],
        'records': records,
    }, 'gpa')


def export_terms(config_path, public_dir):
    """Mirror update_data's requested-term policy, not collected-term membership."""
    config = read(config_path)
    manifest_path = Path(public_dir) / 'integration.json'
    manifest = read(manifest_path)
    require(manifest['schema_version'] == 1 and manifest['dataset'] == 'professor_guide',
            'Invalid integration manifest')
    reference = manifest['files']['history']
    history = read_object(public_dir, reference)
    expected = requested_terms(config['archive_start_year'], config['current_term'])
    require(history['schema_version'] == 2 and history['dataset'] == 'teaching_history',
            'Unsupported teaching-history index')
    require(history['start_year'] == config['archive_start_year']
            and history['through_term'] == config['current_term']
            and history['requested_terms'] == expected
            and manifest['current_term']['id'] == config['current_term'],
            'Configuration and saved history disagree; export stopped')
    rows = history['coverage']['terms']
    require([row['term_id'] for row in rows] == expected
            and all(row['status'] in ('collected', 'unavailable') for row in rows),
            'Invalid saved term coverage')
    return set(expected), {
        'config': config, 'config_sha256': hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
        'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'history_reference': reference,
        'restriction': 'membership in history.requested_terms',
        'allowed_term_status': {row['term_id']: row['status'] for row in rows},
    }


def filter_export(result, allowed):
    """Retain all processing rows; partition only contract-eligible records by term."""
    exported = [row for row in result['normalized_records'] if row['term_id'] in allowed]
    outside = [row for row in result['normalized_records'] if row['term_id'] not in allowed]
    details = []
    for row in result['processing_records']:
        reason = ('source_or_contract_ineligible' if not row['normalized_eligible'] else
                  'term_outside_requested_range' if row['term_id'] not in allowed else None)
        details.append({**row, 'export_exclusion': reason})
    accounting = {**result['accounting'], 'exported_rows': len(exported),
                  'coverage_excluded_rows': len(outside)}
    require(len(exported) + len(outside) + accounting['ineligible_rows'] == len(details),
            'Export row accounting mismatch')
    return exported, details, {
        'accounting': accounting,
        'source_observed_terms': result['observed_terms'],
        'exported_by_term': dict(sorted(Counter(row['term_id'] for row in exported).items())),
        'coverage_excluded_by_term': dict(sorted(Counter(row['term_id'] for row in outside).items())),
    }


def prepare_export(path, provenance_path, *, encoding='utf-8-sig',
                   config_path='config/collection.json', public_dir='public/data'):
    """Build and validate an export in memory, without publication or writes."""
    allowed, history_context = export_terms(config_path, public_dir)
    provenance = read(provenance_path)
    result = import_csv(path, encoding=encoding)
    require(result['source_file_sha256'] == provenance['sha256']
            and result['source_bytes'] == provenance['bytes'],
            'Raw snapshot hash/size disagrees with recorded provenance')
    records, processing, report = filter_export(result, allowed)
    envelope = candidate_envelope(records, source_url=provenance['source_url'],
                                  fetched_at=provenance['fetched_at'])
    report.update(source_provenance=provenance, encoding=encoding,
                  source_file_sha256=result['source_file_sha256'], source_bytes=result['source_bytes'],
                  history=history_context, candidate_validation='passed')
    return {'envelope': envelope, 'processing_records': processing, 'report': report}


def write_export(prepared, output_path, artifacts_dir):
    """Save a validated input and audit artifacts; never replace changed input.

    Callers must put artifacts_dir in ignored local storage. Existing equal
    JSON content is left byte-for-byte untouched, including its formatting.
    """
    envelope = validate_input(prepared['envelope'], 'gpa')
    output_path = Path(output_path)
    body = encoded(envelope)
    exists = output_path.exists()
    if exists:
        require(read(output_path) == envelope,
                'Existing GPA input differs; approval required before replacing it')
        body = output_path.read_bytes()
    executed_at = datetime.now(timezone.utc)
    run_dir = Path(artifacts_dir) / executed_at.strftime('%Y%m%dT%H%M%S%fZ')
    run_dir.mkdir(parents=True, exist_ok=False)
    with (run_dir / 'processing.jsonl').open('xb') as file:
        for record in prepared['processing_records']:
            file.write(encoded(record))
    report = {**prepared['report'], 'export_executed_at': executed_at.isoformat().replace('+00:00', 'Z'),
              'output': {'path': str(output_path), 'sha256': hashlib.sha256(body).hexdigest(),
                         'bytes': len(body), 'existing_content_preserved': exists},
              'processing_artifact': str(run_dir / 'processing.jsonl')}
    if not exists:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open('xb') as file:
            file.write(body)
    with (run_dir / 'export-report.json').open('xb') as file:
        file.write(encoded(report))
    return report, run_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--encoding', default='utf-8-sig',
                        help='Strict decoding; default UTF-8 with optional BOM, no fallback')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--synthetic', action='store_true', help='Confirm input is synthetic')
    mode.add_argument('--source-url', help='Actual HTTPS source URL for an unpublished live candidate')
    mode.add_argument('--provenance', type=Path, help='Recorded source URL, fetch timestamp, raw hash and size')
    parser.add_argument('--fetched-at', help='Actual source fetch timestamp including timezone')
    parser.add_argument('--summary', action='store_true', help='Print accounting/provenance without row arrays')
    parser.add_argument('--export', action='store_true', help='Save a requested-term-filtered input; never publish')
    parser.add_argument('--output', type=Path, default=Path('data/inputs/gpa.json'))
    parser.add_argument('--artifacts-dir', type=Path, help='Ignored local directory for processing/report artifacts')
    parser.add_argument('--config', type=Path, default=Path('config/collection.json'))
    parser.add_argument('--public-dir', type=Path, default=Path('public/data'))
    args = parser.parse_args()
    if args.synthetic and args.fetched_at is not None:
        parser.error('--fetched-at cannot be used with --synthetic')
    if args.provenance and args.fetched_at:
        parser.error('--provenance supplies its own fetch timestamp')
    if args.source_url and not args.fetched_at:
        parser.error('--source-url requires --fetched-at')
    if args.export and (not args.provenance or not args.artifacts_dir):
        parser.error('--export requires --provenance and --artifacts-dir')
    try:
        if args.export:
            prepared = prepare_export(args.csv, args.provenance, encoding=args.encoding,
                                      config_path=args.config, public_dir=args.public_dir)
            report, run_dir = write_export(prepared, args.output, args.artifacts_dir)
            print(json.dumps({'accounting': report['accounting'], 'output': report['output'],
                              'exported_by_term': report['exported_by_term'],
                              'report': str(run_dir / 'export-report.json')}, indent=2))
            return 0
        result = import_csv(args.csv, encoding=args.encoding)
        records = result.pop('normalized_records')
        if args.provenance:
            provenance = read(args.provenance)
            require(result['source_file_sha256'] == provenance['sha256']
                    and result['source_bytes'] == provenance['bytes'], 'Raw snapshot provenance mismatch')
            envelope = candidate_envelope(records, source_url=provenance['source_url'],
                                          fetched_at=provenance['fetched_at'])
        else:
            envelope = (synthetic_envelope(records) if args.synthetic else
                        candidate_envelope(records, source_url=args.source_url, fetched_at=args.fetched_at))
        result['data_kind'] = envelope['data_kind']
        if args.summary:
            result.pop('processing_records')
            result['sources'] = envelope['sources']
            result['collected_at'] = envelope['collected_at']
            result['candidate_validation'] = 'passed'
        else:
            result['normalized'] = envelope
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (DataError, OSError, UnicodeError, LookupError) as error:
        print(f'GPA import failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
