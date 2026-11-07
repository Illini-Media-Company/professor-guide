from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.data_contract import DataError
from scripts.guide_index import build_guide_index
from scripts.integration import attribute_grades, encoded, publish_bundle, read, validate_bundle
from tests.fixtures import fixture_snapshot, archive_fixture
from tests.test_grade_attribution import reviewed_inputs


class GuideIndexTests(unittest.TestCase):
    def build(self, inputs=None):
        inputs = inputs or reviewed_inputs()
        schedule, history = fixture_snapshot(), archive_fixture()
        return build_guide_index(schedule, history, inputs, attribute_grades(schedule, history, inputs))

    def test_all_courses_are_visible_but_only_verified_grades_are_assigned(self):
        index = self.build()
        self.assertEqual(len(index['grade_records']), 1)
        self.assertEqual(index['grade_records'][0]['id'], 'synthetic-zero')
        self.assertEqual(index['grade_records'][0]['gpa'], 0)
        self.assertEqual(index['grade_records'][0]['grain'], 'instructor_course_term')
        self.assertEqual({c['course_code'] for c in index['courses']}, {'CS 374', 'ECE 374'})
        self.assertTrue(any(entry['display_name'] == 'Example, Alex' and
                            any(c['course_code'] == 'ECE 374' for c in entry['courses'])
                            for entry in index['schedule_names']))
        self.assertTrue(all('professor_id' not in entry for entry in index['schedule_names']))
        self.assertNotIn('identity_evidence', index['professors'][0])
        self.assertNotIn('grade_name_matches', str(index))

    def test_missing_ratings_remain_null_and_real_zero_percent_is_preserved(self):
        inputs = reviewed_inputs()
        inputs['professors']['records'][0]['rmp'].update(would_take_again_percent=0, difficulty=None)
        index = self.build(inputs)
        self.assertEqual(index['professors'][0]['rmp']['would_take_again_percent'], 0)
        self.assertIsNone(index['professors'][0]['rmp']['difficulty'])
        inputs['professors']['records'][0]['rmp'] = None
        self.assertIsNone(self.build(inputs)['professors'][0]['rmp'])

    def test_instructors_without_verified_course_links_stay_searchable(self):
        inputs = reviewed_inputs()
        person = deepcopy(inputs['professors']['records'][0])
        person.update(professor_id='synthetic-unlinked', display_name='Unlinked Person')
        inputs['professors']['records'].append(person)
        index = self.build(inputs)
        self.assertEqual(len(index['professors']), 2)
        self.assertEqual(index['professors'][-1]['courses'], [])

    def test_index_is_optional_for_older_pending_bundles(self):
        self.assertIsNone(build_guide_index(fixture_snapshot(), archive_fixture(), {}, {'grade_attributions': []}, schema_version=1))
        index = build_guide_index(fixture_snapshot(), archive_fixture(), {}, {'grade_attributions': [], 'collected_at':fixture_snapshot()['collected_at']})
        self.assertEqual({c['course_code'] for c in index['courses']}, {'CS 374', 'ECE 374'})
        self.assertEqual(index['professors'], [])
        self.assertEqual(index['grade_records'], [])
        self.assertTrue(index['schedule_names'])

    def test_course_without_any_named_instructor_is_still_listed_for_its_term(self):
        schedule = fixture_snapshot()
        for section in schedule['sections']:
            if section['course_code'] == 'ECE 374':
                for meeting in section['meetings']:
                    meeting['instructors'] = []
        index = build_guide_index(schedule, {'snapshots': []}, {}, {'grade_attributions': [], 'collected_at':schedule['collected_at']})
        course = next(c for c in index['courses'] if c['course_code'] == 'ECE 374')
        self.assertIn('2026-fall', course['term_ids'])
        self.assertFalse(any(c['course_code'] == 'ECE 374' for entry in index['schedule_names'] for c in entry['courses']))

    def test_legacy_version_one_keeps_its_original_projection_for_hash_validation(self):
        inputs = reviewed_inputs()
        schedule, history = fixture_snapshot(), archive_fixture()
        legacy = build_guide_index(schedule, history, inputs, attribute_grades(schedule, history, inputs), schema_version=1)
        self.assertEqual(legacy['schema_version'], 1)
        self.assertNotIn('schedule_names', legacy)
        self.assertEqual({c['course_code'] for c in legacy['courses']}, {'CS 374'})

    def test_full_publication_roundtrip_validates_the_derived_index(self):
        inputs = reviewed_inputs()
        with tempfile.TemporaryDirectory() as directory:
            publish_bundle(directory, fixture_snapshot(), archive_fixture(), inputs, allow_fixtures=True)
            _, documents = validate_bundle(directory)
            self.assertEqual(documents['guide'], self.build(inputs))

    def test_earlier_index_without_grain_is_readable_but_changed_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = publish_bundle(root, fixture_snapshot(), archive_fixture(), reviewed_inputs(), allow_fixtures=True)
            guide = read(root / manifest['files']['guide']['path'])
            def rewrite():
                body = encoded(guide)
                digest = hashlib.sha256(body).hexdigest()
                path = f'objects/{digest}.json'
                (root / path).write_bytes(body)
                manifest['files']['guide'].update(path=path, sha256=digest, bytes=len(body))
                (root / 'integration.json').write_bytes(encoded(manifest))
            for row in guide['grade_records']:
                del row['grain']
            rewrite()
            validate_bundle(root)
            guide['grade_records'][0]['gpa'] = 4
            rewrite()
            with self.assertRaisesRegex(DataError, 'visitor guide index'):
                validate_bundle(root)


if __name__ == '__main__':
    unittest.main()
