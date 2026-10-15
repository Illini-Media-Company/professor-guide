from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.campus import department_snapshot
from scripts.collect_course_explorer import CourseExplorerClient
from scripts.course_explorer_discovery import CourseExplorerDiscovery
from scripts.data_contract import AccessDenied, DataError
from scripts.integration import preview, publish_bundle, read, validate_bundle, validate_input
from tests.test_course_explorer import FixtureClient, FIXTURE_TIME, fixture_snapshot
from tests.test_teaching_history import history_fixture


def fixtures():
    base = Path('data/examples/integration')
    return {'gpa': read(base/'gpa.json'), 'professors': read(base/'professors.json'), 'verified_occurrences': read(base/'verified-links.json')}


class IntegrationTests(unittest.TestCase):
    def test_zero_and_unavailable_remain_distinct_and_crnless_grades_stay_crnless(self):
        inputs = fixtures()
        validate_input(inputs['gpa'], 'gpa')
        result = preview(fixture_snapshot(), history_fixture(), inputs)
        self.assertEqual(inputs['gpa']['records'][0]['gpa'], 0)
        self.assertIsNone(inputs['gpa']['records'][1]['gpa'])
        self.assertEqual(result['grade_attributions'][0]['professor_id'], 'synthetic-alex')
        self.assertIsNone(result['grade_attributions'][0]['section_id'])
        self.assertIsNone(result['grade_attributions'][1]['professor_id'])

    def test_primary_order_is_not_identity_or_primary_evidence(self):
        inputs = fixtures()
        inputs['verified_occurrences']['records'][0]['is_primary'] = False
        self.assertIsNone(preview(fixture_snapshot(), history_fixture(), inputs)['grade_attributions'][0]['professor_id'])
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
        with self.assertRaises(DataError): preview(fixture_snapshot(), history_fixture(), inputs)

    def test_fixture_production_separation_pending_inputs_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DataError): publish_bundle(directory, fixture_snapshot(), history_fixture())
            manifest = publish_bundle(directory, fixture_snapshot(), history_fixture(), allow_fixtures=True)
            self.assertEqual(manifest['files']['gpa']['status'], 'pending')
            self.assertIsNone(manifest['files']['gpa']['path'])
            validate_bundle(directory)
            path = Path(directory)/manifest['files']['schedule']['path']
            path.write_text('{}')
            with self.assertRaises(DataError): validate_bundle(directory)

    def test_cached_publication_is_identical_and_failed_manifest_switch_preserves_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            publish_bundle(directory, fixture_snapshot(), history_fixture(), allow_fixtures=True)
            manifest_path = Path(directory)/'integration.json'
            original = manifest_path.read_bytes()
            publish_bundle(directory, fixture_snapshot(), history_fixture(), allow_fixtures=True)
            self.assertEqual(manifest_path.read_bytes(), original)
            from scripts.integration import atomic_write_text as real_write
            def fail_switch(path, body):
                if Path(path) == manifest_path: raise OSError('Simulated interruption before manifest switch')
                return real_write(path,body)
            with patch('scripts.integration.atomic_write_text', side_effect=fail_switch):
                with self.assertRaises(OSError): publish_bundle(directory, fixture_snapshot(), history_fixture(), fixtures(), allow_fixtures=True)
            self.assertEqual(manifest_path.read_bytes(), original)
            validate_bundle(directory)

    def test_access_denial_stops_without_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('scripts.collect_course_explorer.urlopen', side_effect=HTTPError('https://example.org',403,'Denied',{},None)) as request:
                with self.assertRaises(AccessDenied): CourseExplorerClient(directory).fetch('https://example.org')
                self.assertEqual(request.call_count,1)

    def test_cascade_batch_keeps_actual_response_provenance(self):
        import xml.etree.ElementTree as ET
        class BatchFixture(FixtureClient):
            def fetch(self, url, **kwargs):
                if '?mode=cascade' not in url: return super().fetch(url, **kwargs)
                body = super().fetch(url.replace('CS.xml?mode=cascade','CS/374.xml?mode=detail'))['body']
                root = ET.fromstring(body)
                for e in root.iter(): e.tag = e.tag.rsplit('}',1)[-1]
                root.tag = 'cascadingCourse'
                root.find('detailedSections/detailedSection').remove(root.find('detailedSections/detailedSection/sectionNumber'))
                subject = ET.Element('subject',id='CS')
                ET.SubElement(subject,'cascadingCourses').append(root)
                return {'url':url,'fetched_at':FIXTURE_TIME,'body':ET.tostring(subject,encoding='unicode')}
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


if __name__ == '__main__': unittest.main()
