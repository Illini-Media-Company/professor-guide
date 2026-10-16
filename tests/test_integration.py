from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.collect_campus import department_snapshot
from scripts.course_explorer import CourseExplorerClient
from scripts.course_explorer_discovery import CourseExplorerDiscovery
from scripts.data_contract import AccessDenied, DataError
from scripts.integration import attribute_grades, publish_bundle, read, validate_bundle, validate_input
from tests.fixtures import FixtureClient, FIXTURES, FIXTURE_TIME, archive_fixture, fixture_snapshot


def fixtures():
    base = Path('data/examples/integration')
    return {'gpa': read(base/'gpa.json'), 'professors': read(base/'professors.json'), 'verified_occurrences': read(base/'verified-links.json')}


class IntegrationTests(unittest.TestCase):
    def test_zero_and_unavailable_remain_distinct_and_crnless_grades_stay_crnless(self):
        inputs = fixtures()
        validate_input(inputs['gpa'], 'gpa')
        result = attribute_grades(fixture_snapshot(), archive_fixture(), inputs)
        self.assertEqual(inputs['gpa']['records'][0]['gpa'], 0)
        self.assertIsNone(inputs['gpa']['records'][1]['gpa'])
        self.assertEqual(result['grade_attributions'][0]['professor_id'], 'synthetic-alex')
        self.assertIsNone(result['grade_attributions'][0]['section_id'])
        self.assertIsNone(result['grade_attributions'][1]['professor_id'])

    def test_primary_order_is_not_identity_or_primary_evidence(self):
        inputs = fixtures()
        inputs['verified_occurrences']['records'][0]['is_primary'] = False
        self.assertIsNone(attribute_grades(fixture_snapshot(), archive_fixture(), inputs)['grade_attributions'][0]['professor_id'])
        inputs['verified_occurrences']['records'][0]['is_primary'] = True
        del inputs['verified_occurrences']['records'][0]['primary_evidence']
        with self.assertRaises(DataError): validate_input(inputs['verified_occurrences'], 'verified_occurrences')

    def test_uncertain_link_and_course_specific_rmp_are_rejected(self):
        inputs = fixtures()
        inputs['verified_occurrences']['records'][0]['verified'] = False
        with self.assertRaises(DataError): validate_input(inputs['verified_occurrences'], 'verified_occurrences')
        inputs['professors']['records'][0]['rmp']['scope'] = 'course'
        with self.assertRaises(DataError): validate_input(inputs['professors'], 'professors')

    def test_wrong_occurrence_cannot_receive_verified_identity(self):
        inputs = fixtures()
        inputs['verified_occurrences']['records'][0]['name_raw'] = 'Wrong, Person'
        with self.assertRaises(DataError): attribute_grades(fixture_snapshot(), archive_fixture(), inputs)

    def test_fixture_production_separation_pending_inputs_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DataError): publish_bundle(directory, fixture_snapshot(), archive_fixture())
            manifest = publish_bundle(directory, fixture_snapshot(), archive_fixture(), allow_fixtures=True)
            self.assertEqual(manifest['files']['gpa']['status'], 'pending')
            self.assertIsNone(manifest['files']['gpa']['path'])
            validate_bundle(directory)
            path = Path(directory)/manifest['files']['schedule']['path']
            path.write_text('{}')
            with self.assertRaises(DataError): validate_bundle(directory)

    def test_cached_publication_is_identical_and_failed_manifest_switch_preserves_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            publish_bundle(directory, fixture_snapshot(), archive_fixture(), allow_fixtures=True)
            manifest_path = Path(directory)/'integration.json'
            original = manifest_path.read_bytes()
            publish_bundle(directory, fixture_snapshot(), archive_fixture(), allow_fixtures=True)
            self.assertEqual(manifest_path.read_bytes(), original)
            from scripts.integration import atomic_write_text as real_write
            def fail_switch(path, body):
                if Path(path) == manifest_path: raise OSError('Simulated interruption before manifest switch')
                return real_write(path,body)
            with patch('scripts.integration.atomic_write_text', side_effect=fail_switch):
                with self.assertRaises(OSError): publish_bundle(directory, fixture_snapshot(), archive_fixture(), fixtures(), allow_fixtures=True)
            self.assertEqual(manifest_path.read_bytes(), original)
            validate_bundle(directory)

    def test_retention_keeps_two_distinct_publications_and_noop_preserves_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            manifests = []
            for version in range(3):
                schedule = fixture_snapshot()
                schedule['courses'][0]['title'] = f'Synthetic title {version}'
                manifests.append(publish_bundle(directory, schedule, archive_fixture(current=schedule), allow_fixtures=True))
            expected = {item['path'] for manifest in manifests[-2:] for item in manifest['files'].values()
                        if item['status'] == 'available'}
            for manifest in manifests[-2:]:
                history = read(Path(directory)/manifest['files']['history']['path'])
                expected.update(item['path'] for row in history['coverage']['terms'] if row['status'] == 'collected'
                                for item in (row['snapshot'], row['department_coverage']))
            actual = {f'objects/{path.name}' for path in (Path(directory)/'objects').glob('*.json')}
            self.assertEqual(actual, expected)
            self.assertNotIn(manifests[0]['files']['schedule']['path'], actual)
            publish_bundle(directory, schedule, archive_fixture(current=schedule), allow_fixtures=True)
            self.assertEqual({f'objects/{path.name}' for path in (Path(directory)/'objects').glob('*.json')}, expected)
            # A failed switch cannot prune the currently retained generations.
            before = {path: (Path(directory)/path).read_bytes() for path in expected}
            schedule['courses'][0]['title'] = 'Interrupted synthetic refresh'
            from scripts.integration import atomic_write_text as real_write
            def fail_switch(path, body):
                if Path(path) == Path(directory)/'integration.json':
                    raise OSError('Simulated failed switch')
                return real_write(path, body)
            with patch('scripts.integration.atomic_write_text', side_effect=fail_switch):
                with self.assertRaises(OSError):
                    publish_bundle(directory, schedule, archive_fixture(current=schedule), allow_fixtures=True)
            for path, body in before.items():
                self.assertEqual((Path(directory)/path).read_bytes(), body)
            validate_bundle(directory)

    def test_pruning_failure_does_not_fail_a_completed_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            schedule = fixture_snapshot()
            for version in range(2):
                schedule['courses'][0]['title'] = f'Synthetic title {version}'
                manifest = publish_bundle(directory, schedule, archive_fixture(current=schedule), allow_fixtures=True)
                if version == 0:
                    obsolete = Path(directory)/manifest['files']['schedule']['path']
            schedule['courses'][0]['title'] = 'Latest synthetic title'
            real_unlink = Path.unlink
            def fail_old_object(path, *args, **kwargs):
                if path == obsolete:
                    raise OSError('Simulated cleanup permission error')
                return real_unlink(path, *args, **kwargs)
            with patch('pathlib.Path.unlink', fail_old_object):
                with self.assertWarnsRegex(UserWarning, 'Published successfully'):
                    manifest = publish_bundle(directory, schedule, archive_fixture(current=schedule), allow_fixtures=True)
            self.assertEqual(read(Path(directory)/'integration.json'), manifest)
            _, documents = validate_bundle(directory)
            self.assertEqual(documents['schedule']['courses'][0]['title'], 'Latest synthetic title')

    def test_access_denial_stops_without_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('scripts.course_explorer.urlopen', side_effect=HTTPError('https://example.org',403,'Denied',{},None)) as request:
                with self.assertRaises(AccessDenied): CourseExplorerClient(directory).fetch('https://example.org')
                self.assertEqual(request.call_count,1)

    def test_http_202_access_challenge_stops_before_parsing_or_retrying(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.status = 202
        response.__enter__.return_value.headers = {'x-amzn-waf-action': 'challenge'}
        with tempfile.TemporaryDirectory() as directory:
            with patch('scripts.course_explorer.urlopen', return_value=response) as request:
                with self.assertRaisesRegex(AccessDenied, 'challenge'):
                    CourseExplorerClient(directory).fetch('https://courses.illinois.edu/example')
                request.assert_called_once()
                response.__enter__.return_value.read.assert_not_called()
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cascade_batch_keeps_actual_response_provenance(self):
        import xml.etree.ElementTree as ET
        class BatchFixture(FixtureClient):
            def fetch(self, url, **kwargs):
                response = super().fetch(url, **kwargs)
                if url.endswith('CS.xml?mode=cascade'):
                    root = ET.fromstring(response['body'])
                    section = root.find('cascadingCourses/cascadingCourse/detailedSections/detailedSection')
                    section.remove(section.find('sectionNumber'))
                    response['body'] = ET.tostring(root, encoding='unicode')
                return response
        discovery = CourseExplorerDiscovery(BatchFixture())
        term,_ = discovery.term(2026,'fall')
        snapshot = department_snapshot(discovery,term,'CS')
        self.assertEqual(snapshot['sections'][0]['section_label_status'],'missing')
        self.assertTrue(snapshot['courses'][0]['detail_response_url'].endswith('?mode=cascade'))
        self.assertEqual(snapshot['sources'][1]['url'],snapshot['courses'][0]['detail_response_url'])
        self.assertEqual(len(snapshot['sections'][0]['meetings'][0]['instructors']),2)

    def test_explicit_empty_source_states_do_not_create_assignments(self):
        from scripts.data_contract import validate_snapshot
        snapshot = fixture_snapshot()
        snapshot['sections'][0]['meetings'] = []
        snapshot['sections'][0]['meeting_status'] = 'empty'
        validate_snapshot(snapshot)
        snapshot['courses'][0]['section_ids'] = []
        snapshot['courses'][0]['schedule_status'] = 'no_sections'
        snapshot['sections'] = [section for section in snapshot['sections'] if section['course_code'] != 'CS 374']
        validate_snapshot(snapshot)

    def test_reviewed_aliases_require_official_evidence_and_terms(self):
        from scripts.integration import validate_reviewed_aliases
        mapping = {'schema_version':1,'aliases':[{'course_codes':['CS 374','ECE 374'],'term_ids':['2026-fall'],'reviewed_by':'Synthetic reviewer','reviewed_at':FIXTURE_TIME,'evidence':[{'text':'Same as ECE 374.','source_url':'https://courses.illinois.edu/example'}]}]}
        validate_reviewed_aliases(mapping)
        mapping['aliases'][0]['term_ids'] = []
        with self.assertRaises(DataError): validate_reviewed_aliases(mapping)

    def test_source_times_are_compared_chronologically_across_offsets(self):
        inputs = fixtures()
        inputs['gpa']['collected_at'] = '2025-12-31T19:00:01-05:00'
        result = attribute_grades(fixture_snapshot(),archive_fixture(),inputs)
        self.assertEqual(result['collected_at'],inputs['gpa']['collected_at'])
        with tempfile.TemporaryDirectory() as directory:
            manifest = publish_bundle(directory,fixture_snapshot(),archive_fixture(),inputs,allow_fixtures=True)
            self.assertEqual(manifest['collected_at'],inputs['gpa']['collected_at'])
            validate_bundle(directory)

    def test_long_retry_after_defers_update_instead_of_ignoring_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            error = HTTPError('https://example.org',429,'Limited',{'Retry-After':'120'},None)
            with patch('scripts.course_explorer.urlopen',side_effect=error) as request:
                with self.assertRaisesRegex(DataError,'defer'): CourseExplorerClient(directory).fetch('https://example.org')
                self.assertEqual(request.call_count,1)

    def test_offline_reuse_does_not_fetch_missing_grade_history(self):
        from scripts.archive import collect_archive
        from unittest.mock import MagicMock
        client = MagicMock()
        with self.assertRaisesRegex(DataError, 'not archived'):
            collect_archive(client, 2024, '2026-fall', allow_collection=False)
        client.fetch.assert_not_called()

    def test_old_raw_cache_cannot_roll_back_a_newer_persisted_fetch(self):
        from datetime import datetime, timedelta, timezone
        import hashlib
        from scripts.data_contract import atomic_write_json
        from unittest.mock import MagicMock
        url = 'https://courses.illinois.edu/cisapp/explorer/schedule/2026/fall/CS/374.xml'
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            atomic_write_json(Path(directory)/(hashlib.sha256(url.encode()).hexdigest()+'.json'),{'url':url,'fetched_at':(now-timedelta(minutes=2)).isoformat(),'body':(FIXTURES/'cs-detail.xml').read_text()})
            client = CourseExplorerClient(directory)
            client.minimum_fetch_times[url] = (now-timedelta(minutes=1)).isoformat()
            response = MagicMock()
            response.__enter__.return_value.status = 200
            response.__enter__.return_value.read.return_value = (FIXTURES/'cs-detail.xml').read_bytes()
            with patch('scripts.course_explorer.urlopen',return_value=response) as request:
                client.fetch(url)
                self.assertEqual(request.call_count,1)


if __name__ == '__main__': unittest.main()
