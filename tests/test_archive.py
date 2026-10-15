"""Small fixtures exercise archive completeness, nested hashes, and failure safety."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.archive import (collect_archive, requested_terms, totals, validate_archive,
                             validate_department_coverage)
from scripts.data_contract import API_BASE, DataError, RequestError
from scripts.integration import load_term, publish_bundle, read, validate_bundle
from scripts.teaching_history import counts
from tests.test_teaching_history import history_fixture


def archive_fixture():
    old = history_fixture()
    snapshots = sorted(old['snapshots'], key=lambda snapshot: requested_terms(2025, '2026-fall').index(snapshot['term']['id']))
    by_term = {snapshot['term']['id']: snapshot for snapshot in snapshots}
    department_coverage = {}
    for term, snapshot in by_term.items():
        subjects = sorted({course['course_code'].split()[0] for course in snapshot['courses']})
        department_coverage[term] = {'term_id': term, 'discovered_subjects': subjects, 'requested_subjects': subjects,
            'departments': [{'subject': subject, 'status': 'collected',
                            'course_count': sum(course['course_code'].startswith(subject+' ') for course in snapshot['courses']),
                            **counts([section for section in snapshot['sections'] if section['course_code'].startswith(subject+' ')])}
                           for subject in subjects]}
    sources = old['discovery_sources']
    source_times = {source['url']: source['fetched_at'] for source in sources}
    rows = []
    for term in requested_terms(2025, '2026-fall'):
        url = f'{API_BASE}/{term.split("-")[0]}.xml'
        row = {'term_id': term, 'source_url': url, 'checked_at': source_times[url],
               'status': 'unavailable', 'reason': 'term_not_listed', 'department_count': 0, 'course_count': 0, **counts([])}
        if term in by_term:
            snapshot = by_term[term]
            row.update(status='collected', reason='term_listed', term=snapshot['term'],
                       department_count=len(department_coverage[term]['departments']),
                       course_count=len(snapshot['courses']), **counts(snapshot['sections']))
        rows.append(row)
    return validate_archive({'schema_version': 2, 'dataset': 'teaching_history', 'data_kind': 'development_fixture',
        'start_year': 2025, 'through_term': '2026-fall', 'requested_terms': requested_terms(2025, '2026-fall'),
        'collected_at': old['collected_at'], 'discovery_sources': sources, 'snapshots': snapshots,
        'department_coverage': department_coverage, 'coverage': {'terms': rows, 'totals': totals(rows)}})


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
            from tests.test_course_explorer import FixtureClient
            # First discovered term is accepted; the next term fails during collection.
            current = history['snapshots'][1]
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
