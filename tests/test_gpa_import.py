"""Synthetic, offline checks of row-preserving GPA import and arithmetic."""

import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from scripts.data_contract import DataError
from scripts.import_gpa import (COLUMNS, GRADE_POINTS, candidate_envelope, export_terms,
                                filter_export, import_csv, prepare_export, synthetic_envelope, write_export)
from scripts.archive import requested_terms
from scripts.integration import encoded, validate_input


FIXTURE = Path('data/examples/gpa/tiny-synthetic.csv')


def source_row(**changes):
    row = next(csv.DictReader(io.StringIO(FIXTURE.read_text(encoding='utf-8'))))
    row.update(changes)
    return row


def parse_rows(*rows):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'synthetic.csv'
        with path.open('w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return import_csv(path)


def saved_history(root):
    """Small synthetic index; no live schedules or source requests."""
    config = {'archive_start_year': 2023, 'current_term': '2024-spring'}
    terms = requested_terms(2023, '2024-spring')
    history = {'schema_version': 2, 'dataset': 'teaching_history',
               'data_kind': 'development_fixture', 'start_year': 2023,
               'through_term': '2024-spring', 'requested_terms': terms,
               'coverage': {'terms': [{'term_id': term, 'status': 'unavailable' if term == terms[0] else 'collected'}
                                      for term in terms]}}
    body = encoded(history)
    digest = hashlib.sha256(body).hexdigest()
    public = root / 'public'
    (public / 'objects').mkdir(parents=True)
    (public / 'objects' / f'{digest}.json').write_bytes(body)
    reference = {'status': 'available', 'path': f'objects/{digest}.json',
                 'sha256': digest, 'bytes': len(body), 'collected_at': '2026-01-01T00:00:00Z'}
    manifest = {'schema_version': 1, 'dataset': 'professor_guide',
                'current_term': {'id': config['current_term']}, 'files': {'history': reference}}
    (public / 'integration.json').write_bytes(encoded(manifest))
    config_path = root / 'config.json'
    config_path.write_bytes(encoded(config))
    return config_path, public, reference


class GPAImportTests(unittest.TestCase):
    def test_export_boundaries_and_requested_unavailable_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path, public, _ = saved_history(Path(directory))
            allowed, context = export_terms(config_path, public)
            self.assertIn('2023-winter', allowed)
            self.assertEqual(context['allowed_term_status']['2023-winter'], 'unavailable')
            rows = [source_row(Year=year, Term=term) for year, term in
                    [('2022', 'Fall'), ('2023', 'Winter'), ('2024', 'Spring'), ('2024', 'Summer')]]
            exported, processing, report = filter_export(parse_rows(*rows), allowed)
            self.assertEqual([r['term_id'] for r in exported], ['2023-winter', '2024-spring'])
            self.assertEqual(report['accounting']['coverage_excluded_rows'], 2)
            self.assertEqual(len(processing), 4)
            synthetic_envelope(exported)

    def test_export_stops_on_history_config_disagreement_or_corrupt_object(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, public, reference = saved_history(root)
            config_path.write_bytes(encoded({'archive_start_year': 2023, 'current_term': '2024-fall'}))
            with self.assertRaisesRegex(DataError, 'disagree'):
                export_terms(config_path, public)
            config_path.write_bytes(encoded({'archive_start_year': 2023, 'current_term': '2024-spring'}))
            (public / reference['path']).write_bytes(b'{}')
            with self.assertRaisesRegex(DataError, 'hash/size mismatch'):
                export_terms(config_path, public)

    def test_export_keeps_contract_and_coverage_exclusions_separate(self):
        valid = source_row()
        bad = source_row(Subject='MATH', Number='2', Year='2022')
        blank = source_row(**{'Primary Instructor': ''})
        result = parse_rows(valid, valid, bad, blank, source_row(Year='2022'))
        exported, processing, report = filter_export(result, {'2025-spring'})
        accounting = report['accounting']
        self.assertEqual(accounting['parsed_rows'], 5)
        self.assertEqual(accounting['ineligible_rows'], 2)
        self.assertEqual(accounting['coverage_excluded_rows'], 1)
        self.assertEqual(accounting['exported_rows'], 2)
        self.assertEqual([r['export_exclusion'] for r in processing],
                         [None, None, 'source_or_contract_ineligible',
                          'source_or_contract_ineligible', 'term_outside_requested_range'])
        self.assertNotEqual(exported[0]['id'], exported[1]['id'])

    def test_prepared_export_is_deterministic_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, public, _ = saved_history(root)
            # Empty source tests live provenance without relabeling synthetic grade rows.
            source = root / 'empty.csv'
            source.write_bytes((','.join(COLUMNS) + '\n').encode('utf-8'))
            provenance = {'source_url': 'https://example.org/provenance-test.csv',
                          'fetched_at': '2026-10-30T21:15:43.172904Z',
                          'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                          'bytes': len(source.read_bytes())}
            provenance_path = root / 'provenance.json'
            provenance_path.write_bytes(encoded(provenance))
            args = dict(config_path=config_path, public_dir=public, encoding='utf-8')
            first = prepare_export(source, provenance_path, **args)
            second = prepare_export(source, provenance_path, **args)
            self.assertEqual(first, second)
            self.assertEqual(encoded(first['envelope']), encoded(second['envelope']))
            envelope = first['envelope']
            self.assertEqual(envelope['collected_at'], provenance['fetched_at'])
            self.assertEqual(envelope['sources'], [{'url': provenance['source_url'],
                                                   'fetched_at': provenance['fetched_at']}])
            validate_input(envelope, 'gpa')
            self.assertEqual(first['report']['source_provenance'], provenance)
            source.write_bytes(source.read_bytes() + b'\n')
            with self.assertRaisesRegex(DataError, 'hash/size'):
                prepare_export(source, provenance_path, **args)

    def test_export_writer_preserves_equal_input_and_refuses_changed_input(self):
        result = import_csv(FIXTURE)
        records, processing, report = filter_export(result, {'2025-spring'})
        prepared = {'envelope': synthetic_envelope(records), 'processing_records': processing,
                    'report': report}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, artifacts = root / 'gpa.json', root / 'artifacts'
            first_report, run_dir = write_export(prepared, output, artifacts)
            before = output.read_bytes()
            self.assertEqual(before, encoded(prepared['envelope']))
            self.assertEqual(len((run_dir / 'processing.jsonl').read_bytes().splitlines()), 1)
            self.assertTrue((run_dir / 'export-report.json').exists())
            second_report, _ = write_export(prepared, output, artifacts)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(first_report['output']['sha256'], second_report['output']['sha256'])
            self.assertTrue(second_report['output']['existing_content_preserved'])
            changed = {**prepared, 'envelope': synthetic_envelope([])}
            with self.assertRaisesRegex(DataError, 'approval required'):
                write_export(changed, output, artifacts)
            self.assertEqual(output.read_bytes(), before)

    def test_explicit_windows1252_decoding_preserves_name_and_raw_hash(self):
        path = FIXTURE.with_name('windows1252-synthetic.csv')
        with self.assertRaises(UnicodeDecodeError):
            import_csv(path)
        result = import_csv(path, encoding='cp1252')
        self.assertEqual(result['encoding'], 'cp1252')
        self.assertEqual(result['source_file_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result['source_bytes'], len(path.read_bytes()))
        self.assertEqual(result['processing_records'][0]['original']['Primary Instructor'], 'Example, José')
        self.assertEqual(result['normalized_records'][0]['primary_instructor_name_raw'], 'Example, José')
        self.assertEqual(result['normalized_records'][0]['gpa'], 2.75)
        synthetic_envelope(result['normalized_records'])

    def test_unsupported_course_is_retained_without_padding_or_export(self):
        result = parse_rows(source_row(Subject='MATH', Number='2'))
        self.assertEqual(result['normalized_records'], [])
        detail = result['processing_records'][0]
        self.assertEqual(detail['original']['Number'], '2')
        self.assertEqual(detail['course_code'], 'MATH 2')
        self.assertEqual((detail['gpa'], detail['student_count'], detail['withdrawals']), (2.75, 4, 1))
        self.assertFalse(detail['normalized_eligible'])
        self.assertEqual(detail['exclusion_reasons'], ['course_code_outside_contract'])

    def test_overlapping_exclusions_and_reviews_have_separate_accounting(self):
        valid = source_row()
        bad_course = source_row(Subject='MATH', Number='2')
        both = dict(bad_course, **{'Primary Instructor': '', 'A': ''})
        missing = source_row(A='')
        result = parse_rows(valid, valid, bad_course, both, missing)
        report = result['accounting']
        self.assertEqual(report['parsed_rows'], 5)
        self.assertEqual(report['eligible_normalized_rows'], 3)
        self.assertEqual(report['ineligible_rows'], 2)
        self.assertEqual(report['exclusion_reason_counts'],
                         {'course_code_outside_contract': 2, 'missing_primary_instructor': 1})
        self.assertEqual(report['review_reason_counts']['missing_letter_grade_counts'], 2)
        self.assertEqual(report['eligible_normalized_rows'] + report['ineligible_rows'], report['parsed_rows'])
        self.assertEqual(len(result['processing_records']), 5)
        self.assertIsNone(result['normalized_records'][-1]['gpa'])
        self.assertIsNone(result['normalized_records'][-1]['student_count'])
        synthetic_envelope(result['normalized_records'])

    def test_ineligible_rows_still_raise_on_malformed_counts_or_structure(self):
        for changes in ({'A': '-1'}, {'Students': '5'}, {'Year': 'not-a-year'}, {'Term': 'unknown'}):
            with self.subTest(changes=changes):
                with self.assertRaises(DataError):
                    parse_rows(source_row(Subject='MATH', Number='2', **changes))

    def test_live_candidate_uses_only_explicit_provenance(self):
        # Empty records exercise the live-envelope path without relabeling fixture rows.
        url = 'https://example.org/live-candidate-provenance-test.csv'
        fetched = '2026-10-30T21:15:43.172904Z'
        envelope = candidate_envelope([], source_url=url, fetched_at=fetched)
        self.assertEqual(envelope['data_kind'], 'live')
        self.assertEqual(envelope['sources'], [{'url': url, 'fetched_at': fetched}])
        self.assertEqual(envelope['collected_at'], fetched)
        validate_input(envelope, 'gpa')
        with self.assertRaises(TypeError):
            candidate_envelope([])
        for url, fetched in (('http://example.org/source', fetched), ('https://', fetched),
                             (url, 'not-a-date'), (url, '2026-10-30T21:15:43')):
            with self.subTest(url=url, fetched=fetched):
                with self.assertRaises(DataError):
                    candidate_envelope([], source_url=url, fetched_at=fetched)

    def test_fixture_calculation_withdrawals_and_contract(self):
        result = import_csv(FIXTURE)
        detail = result['processing_records'][0]
        record = result['normalized_records'][0]
        self.assertEqual(detail['weighted_total_hundredths'], 1100)
        self.assertEqual(detail['withdrawals'], 1)
        self.assertEqual(detail['source_students'], 4)
        self.assertEqual((record['gpa'], record['student_count']), (2.75, 4))
        self.assertEqual(record['grain'], 'instructor_course_term')
        self.assertIsNone(record['section_id'])
        self.assertEqual(record['primary_instructor_name_raw'], 'Example, Alex')
        self.assertEqual(set(record), {'id', 'term_id', 'course_code', 'grain',
                                     'section_id', 'primary_instructor_name_raw',
                                     'gpa', 'student_count'})
        envelope = synthetic_envelope(result['normalized_records'])
        self.assertEqual(envelope['data_kind'], 'development_fixture')
        validate_input(envelope, 'gpa')

    def test_each_illinois_grade_point_and_no_intermediate_rounding(self):
        expected = {'A+': 4, 'A': 4, 'A-': 3.67, 'B+': 3.33, 'B': 3,
                    'B-': 2.67, 'C+': 2.33, 'C': 2, 'C-': 1.67,
                    'D+': 1.33, 'D': 1, 'D-': 0.67, 'F': 0}
        for grade, points in expected.items():
            with self.subTest(grade=grade):
                row = source_row(**dict.fromkeys(GRADE_POINTS, '0'))
                row.update({grade: '3', 'Students': '3', 'W': '0'})
                self.assertEqual(parse_rows(row)['normalized_records'][0]['gpa'], points)
        row = source_row(A='1', B='0', F='2', Students='3')
        result = parse_rows(row)
        self.assertEqual(result['processing_records'][0]['weighted_total_hundredths'], 400)
        self.assertEqual(result['normalized_records'][0]['gpa'], 4 / 3)

    def test_missing_grade_counts_never_become_zero_or_partial_totals(self):
        for missing in ('', '  '):
            with self.subTest(missing=missing):
                result = parse_rows(source_row(A=missing))
                detail = result['processing_records'][0]
                record = result['normalized_records'][0]
                self.assertIsNone(detail['grade_counts']['A'])
                self.assertIsNone(detail['weighted_total_hundredths'])
                self.assertEqual(detail['source_students'], 4)
                self.assertIn('missing_letter_grade_counts', detail['review_reasons'])
                self.assertIsNone(record['gpa'])
                self.assertIsNone(record['student_count'])
                synthetic_envelope(result['normalized_records'])

    def test_malformed_counts_are_errors_even_with_other_missing_counts(self):
        for column in (*GRADE_POINTS, 'W', 'Students'):
            for value in ('-1', '1.5', 'NaN', 'inf', 'unknown', '1.0'):
                with self.subTest(column=column, value=value):
                    row = source_row(**{'A+': '', column: value})
                    with self.assertRaisesRegex(DataError, 'Record 1:'):
                        parse_rows(row)

    def test_students_mismatch_is_rejected_when_grades_complete(self):
        with self.assertRaisesRegex(DataError, 'Students disagrees'):
            parse_rows(source_row(Students='5'))

    def test_missing_students_or_withdrawals_do_not_destroy_complete_grades(self):
        detail = parse_rows(source_row(Students='', W=''))['processing_records'][0]
        self.assertIsNone(detail['source_students'])
        self.assertIsNone(detail['withdrawals'])
        self.assertEqual((detail['student_count'], detail['gpa']), (4, 2.75))

    def test_zero_enrollment_and_all_f_are_distinct(self):
        empty = source_row(**dict.fromkeys(GRADE_POINTS, '0'))
        empty.update(Students='0', W='2')
        failing = dict(empty, F='3', Students='3')
        records = parse_rows(empty, failing)['normalized_records']
        self.assertEqual(records[0]['student_count'], 0)
        self.assertIsNone(records[0]['gpa'])
        self.assertEqual((records[1]['gpa'], records[1]['student_count']), (0, 3))
        synthetic_envelope(records)

    def test_original_values_positions_and_identical_rows_are_preserved(self):
        row = source_row(**{'Primary Instructor': '  Example, Alex  ',
                            'Course Title': 'Synthetic café\nsecond line', 'A': ' 2 '})
        result = parse_rows(row, row, dict(row, Subject='ECE'))
        details, records = result['processing_records'], result['normalized_records']
        self.assertEqual(len(details), 3)
        self.assertEqual(len(records), 3)
        self.assertEqual([item['source_record_position'] for item in details], [1, 2, 3])
        self.assertEqual(details[0]['original'], row)
        self.assertEqual(details[1]['original'], row)
        self.assertNotEqual(records[0]['id'], records[1]['id'])
        self.assertEqual([record['course_code'] for record in records], ['CS 101', 'CS 101', 'ECE 101'])
        self.assertEqual([record['student_count'] for record in records], [4, 4, 4])

    def test_blank_instructor_stays_in_processing_only(self):
        for name in ('', '  '):
            with self.subTest(name=name):
                result = parse_rows(source_row(**{'Primary Instructor': name}))
                self.assertEqual(result['normalized_records'], [])
                self.assertEqual(len(result['processing_records']), 1)
                detail = result['processing_records'][0]
                self.assertEqual(detail['gpa'], 2.75)
                self.assertEqual(detail['original']['Primary Instructor'], name)
                self.assertIn('missing_primary_instructor', detail['review_reasons'])

    def test_winter_uses_given_ending_year_and_preserves_source_yearterm(self):
        row = source_row(Year='2026', Term='Winter', YearTerm='2026-wi')
        result = parse_rows(row)
        self.assertEqual(result['normalized_records'][0]['term_id'], '2026-winter')
        self.assertEqual(result['processing_records'][0]['original']['YearTerm'], '2026-wi')

    def test_ids_are_deterministic_and_include_exact_source_hash(self):
        first, second = import_csv(FIXTURE), import_csv(FIXTURE)
        self.assertEqual(first, second)
        expected = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        detail = first['processing_records'][0]
        self.assertEqual(detail['source_file_sha256'], expected)
        self.assertEqual(detail['id'], f'{expected}:row-1')
        changed = parse_rows(source_row(**{'Course Title': 'Different synthetic title'}))
        self.assertNotEqual(changed['normalized_records'][0]['id'], detail['id'])

    def test_unexpected_header_and_incomplete_csv_rows_are_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.csv'
            for body in ('Year,Term\n2025,Spring\n', ','.join(COLUMNS) + '\n2025,Spring\n'):
                with self.subTest(body=body):
                    path.write_bytes(body.encode('utf-8'))
                    with self.assertRaises(DataError):
                        import_csv(path)


if __name__ == '__main__':
    unittest.main()
