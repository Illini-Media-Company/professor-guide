"""Small fixtures exercise archive completeness, nested hashes, and failure safety."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.archive import (collect_archive, render_archive_report, requested_terms, validate_archive,
                             validate_department_coverage)
from scripts.data_contract import DataError, RequestError, counts
from scripts.integration import load_term, publish_bundle, read, validate_bundle
from tests.fixtures import FixtureClient, archive_fixture


class ArchiveTests(unittest.TestCase):
    def test_range_and_unavailable_terms_do_not_create_fake_assignments(self):
        history = archive_fixture()
        self.assertEqual(len(requested_terms(2023, '2026-fall')), 16)
        self.assertEqual(history['coverage']['totals']['collected_terms'], 2)
        self.assertEqual(history['coverage']['totals']['unavailable_terms'], 6)
        self.assertEqual(len(history['snapshots']), 2)
        history['coverage']['terms'].pop()
        with self.assertRaisesRegex(DataError, 'Incomplete'):
            validate_archive(history)

    def test_multi_term_records_keep_original_names_roles_and_separate_crns(self):
        history = archive_fixture()
        spring, fall = history['snapshots']
        self.assertEqual([snapshot['term']['id'] for snapshot in history['snapshots']], ['2025-spring', '2026-fall'])
        self.assertEqual(spring['sections'][0]['crn'], fall['sections'][0]['crn'])
        self.assertNotEqual(spring['sections'][0]['id'], fall['sections'][0]['id'])
        stats = history['coverage']['totals']
        self.assertEqual((stats['section_count'], stats['meeting_count']), (8, 10))
        self.assertEqual((stats['missing_instructor_meetings'], stats['multiple_instructor_meetings'], stats['unresolved_occurrences']), (4, 4, 10))
        self.assertEqual(counts([section for snapshot in history['snapshots'] for section in snapshot['sections']])['meeting_types'], {'DIS': 2, 'LAB': 4, 'LEC': 4})
        self.assertEqual(fall['relationships'][0]['to_listing_id'], '2026-fall:ECE 374')
        self.assertEqual(fall['sections'][0]['meetings'][0]['instructors'][0]['name_raw'], 'Example, Alex')
        self.assertIn('not unique people', render_archive_report(history))

    def test_unavailable_year_has_explicit_coverage_and_no_invented_assignments(self):
        history = collect_archive(FixtureClient(), 2024, '2024-fall')
        self.assertEqual(history['snapshots'], [])
        self.assertEqual(history['coverage']['totals']['unavailable_terms'], 4)
        self.assertTrue(all(row['reason'] == 'year_not_listed' for row in history['coverage']['terms']))
        validate_archive(history)

    def test_tampered_counts_and_provenance_cannot_replace_published_archive(self):
        history = archive_fixture()
        with tempfile.TemporaryDirectory() as directory:
            publish_bundle(directory, history['snapshots'][-1], history, allow_fixtures=True)
            before = (Path(directory)/'integration.json').read_bytes()
            for mutate in (
                lambda data: data['coverage']['terms'][1].update(section_count=999),
                lambda data: data['coverage']['terms'].pop(),
                lambda data: data['coverage']['terms'][1].update(source_url='https://example.org/'),
                lambda data: data['coverage']['totals'].update(unresolved_occurrences=0),
                lambda data: data.update(schema_version=1),
            ):
                invalid = deepcopy(history)
                mutate(invalid)
                with self.subTest(mutate=mutate), self.assertRaises(DataError):
                    publish_bundle(directory, invalid['snapshots'][-1], invalid, allow_fixtures=True)
                self.assertEqual((Path(directory)/'integration.json').read_bytes(), before)
            validate_bundle(directory)

    def test_partial_department_collection_is_rejected(self):
        history = archive_fixture()
        snapshot = history['snapshots'][0]
        coverage = deepcopy(history['department_coverage'][snapshot['term']['id']])
        coverage['requested_subjects'] = coverage['requested_subjects'][:1]
        with self.assertRaisesRegex(DataError, 'every discovered department'):
            validate_department_coverage(snapshot, coverage)

    def test_index_roundtrip_preserves_source_data_and_validates_nested_hashes(self):
        history = archive_fixture()
        schedule = history['snapshots'][-1]
        with tempfile.TemporaryDirectory() as directory:
            manifest = publish_bundle(directory, schedule, history, allow_fixtures=True)
            index = read(Path(directory)/manifest['files']['history']['path'])
            self.assertNotIn('snapshots', index)
            rows = [row for row in index['coverage']['terms'] if row['status'] == 'collected']
            self.assertEqual(len(rows), 2)
            _, files = validate_bundle(directory)
            self.assertEqual(files['history'], history)
            self.assertEqual(load_term(directory, '2025-spring'), history['snapshots'][0])
            with self.assertRaisesRegex(DataError, 'unavailable'):
                load_term(directory, '2025-summer')
            with self.assertRaisesRegex(DataError, 'outside'):
                load_term(directory, '2022-fall')
            nested = Path(directory)/rows[-1]['snapshot']['path']
            nested.write_text('{}')
            with self.assertRaisesRegex(DataError, 'hash/size'):
                validate_bundle(directory)

    def test_offline_reuse_and_late_network_failure_preserve_published_archive(self):
        history = archive_fixture()
        with tempfile.TemporaryDirectory() as directory:
            publish_bundle(directory, history['snapshots'][-1], history, allow_fixtures=True)
            before = (Path(directory)/'integration.json').read_bytes()
            client = MagicMock()
            self.assertIs(collect_archive(client, 2025, '2026-fall', existing=history, allow_collection=False), history)
            client.fetch.assert_not_called()
            # Reuse the first term, then fail while collecting the current term.
            current = deepcopy(history['snapshots'][0])
            current['data_kind'] = 'live'
            coverage = history['department_coverage'][current['term']['id']]
            with patch('scripts.collect_campus.collect', side_effect=RequestError('Simulated exhausted timeout')):
                with self.assertRaisesRegex(RequestError, 'exhausted timeout'):
                    collect_archive(FixtureClient(), 2025, '2026-fall', current=(current, coverage),
                                    candidate_dir=Path(directory)/'candidates')
            self.assertEqual((Path(directory)/'integration.json').read_bytes(), before)
            validate_bundle(directory)

    def test_pruning_keeps_nested_objects_of_the_previous_generation(self):
        history = archive_fixture()
        with tempfile.TemporaryDirectory() as directory:
            first = publish_bundle(directory, history['snapshots'][-1], history, allow_fixtures=True)
            index = read(Path(directory)/first['files']['history']['path'])
            paths = [row['snapshot']['path'] for row in index['coverage']['terms'] if row['status'] == 'collected']
            changed = deepcopy(history)
            changed['snapshots'][0]['courses'][0]['title'] = 'Changed synthetic title'
            publish_bundle(directory, changed['snapshots'][-1], changed, allow_fixtures=True)
            for path in paths:
                self.assertTrue((Path(directory)/path).exists())
            validate_bundle(directory)


if __name__ == '__main__':
    unittest.main()
