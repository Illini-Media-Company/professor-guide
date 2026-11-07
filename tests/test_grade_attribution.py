"""Evidence-backed joins across distinct grade and schedule name formats."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from scripts.data_contract import DataError
from scripts.integration import attribute_grades, load_term, publish_bundle, read, validate_bundle, validate_input
from scripts.update_data import teammate_inputs
from tests.fixtures import FIXTURE_TIME, archive_fixture, fixture_snapshot


def reviewed_inputs():
    base = Path('data/examples/integration')
    inputs = {name: read(base / path) for name, path in (
        ('gpa', 'gpa.json'), ('professors', 'professors.json'),
        ('verified_occurrences', 'verified-links.json'))}
    grade = inputs['gpa']['records'][0]
    grade['primary_instructor_name_raw'] = 'Example, Alexandra Q'
    link = inputs['verified_occurrences']['records'][0]
    link.update(is_primary=False, primary_evidence=[], grade_name_matches=[{
        'grade_record_id': grade['id'],
        'primary_instructor_name_raw': grade['primary_instructor_name_raw'],
        'source_url': inputs['gpa']['sources'][0]['url'],
        'reviewed_by': 'Synthetic reviewer', 'verified_at': FIXTURE_TIME,
        'evidence': ['Synthetic faculty evidence connects both source names to this person.'],
        'primary_evidence': ['Synthetic grade source explicitly names Alexandra as primary.'],
    }])
    return inputs


def attribute(inputs):
    return attribute_grades(fixture_snapshot(), archive_fixture(), inputs)['grade_attributions']


class GradeNameAttributionTests(unittest.TestCase):
    def test_reviewed_name_difference_resolves_without_changing_sources_or_section_grain(self):
        inputs = reviewed_inputs()
        original = deepcopy(inputs)
        rows = attribute(inputs)
        self.assertEqual(rows[0]['professor_id'], 'synthetic-alex')
        self.assertEqual(rows[0]['status'], 'verified')
        self.assertIsNone(rows[0]['section_id'])
        self.assertIsNone(rows[1]['professor_id'])
        self.assertEqual(inputs, original)
        self.assertFalse(inputs['verified_occurrences']['records'][0]['is_primary'])

    def test_names_are_not_fuzzily_matched_without_review(self):
        inputs = reviewed_inputs()
        link = inputs['verified_occurrences']['records'][0]
        del link['grade_name_matches']
        link.update(is_primary=True, primary_evidence=['Synthetic explicit schedule-primary evidence'])
        self.assertEqual(attribute(inputs)[0]['status'], 'unresolved')

    def test_review_is_scoped_to_one_grade_row_even_when_names_and_course_match(self):
        inputs = reviewed_inputs()
        grade = deepcopy(inputs['gpa']['records'][0])
        grade['id'] = 'synthetic-separate-row'
        inputs['gpa']['records'].append(grade)
        rows = attribute(inputs)
        self.assertEqual(rows[0]['status'], 'verified')
        self.assertEqual(rows[-1]['status'], 'unresolved')

    def test_stale_grade_ids_and_changed_names_courses_terms_and_sections_are_rejected(self):
        for changes, message in (
            ({'id': 'synthetic-new-snapshot-row'}, 'unknown grade'),
            ({'primary_instructor_name_raw': 'Example, Another Person'}, 'grade source name'),
            ({'course_code': 'ECE 374'}, 'different course/term'),
            ({'term_id': '2025-fall'}, 'different course/term'),
            ({'grain': 'section', 'section_id': '2026-fall:10002'}, 'different section'),
            ({'grain': 'course_term'}, 'aggregates'),
        ):
            with self.subTest(changes=changes):
                inputs = reviewed_inputs()
                inputs['gpa']['records'][0].update(changes)
                with self.assertRaisesRegex(DataError, message):
                    attribute(inputs)

    def test_section_grade_requires_the_actual_section_and_keeps_its_id(self):
        inputs = reviewed_inputs()
        inputs['gpa']['records'][0].update(grain='section', section_id='2026-fall:10001')
        row = attribute(inputs)[0]
        self.assertEqual(row['professor_id'], 'synthetic-alex')
        self.assertEqual(row['section_id'], '2026-fall:10001')

    def test_grade_match_cannot_replace_occurrence_identity_validation(self):
        for changes, message in (
            ({'name_raw': 'Wrong, Person'}, 'preserved source name'),
            ({'professor_id': 'synthetic-unknown'}, 'unknown professor'),
            ({'meeting_id': '2026-fall:10001:99'}, 'unknown instructor occurrence'),
            ({'instructor_index': 99}, 'unknown instructor occurrence'),
            ({'verified': False}, 'Uncertain matches'),
        ):
            with self.subTest(changes=changes):
                inputs = reviewed_inputs()
                inputs['verified_occurrences']['records'][0].update(changes)
                with self.assertRaisesRegex(DataError, message):
                    attribute(inputs)

    def test_grade_matches_require_review_identity_and_primary_evidence(self):
        for key in ('evidence', 'primary_evidence'):
            for invalid in (None, [], [''], ['  '], 'unsupported evidence', [True], [{}]):
                with self.subTest(key=key, invalid=invalid):
                    inputs = reviewed_inputs()
                    inputs['verified_occurrences']['records'][0]['grade_name_matches'][0][key] = invalid
                    with self.assertRaises(DataError):
                        validate_input(inputs['verified_occurrences'], 'verified_occurrences')
        for key in ('grade_record_id', 'primary_instructor_name_raw', 'reviewed_by',
                    'verified_at', 'source_url', 'evidence', 'primary_evidence'):
            with self.subTest(missing=key):
                inputs = reviewed_inputs()
                del inputs['verified_occurrences']['records'][0]['grade_name_matches'][0][key]
                with self.assertRaises(DataError):
                    validate_input(inputs['verified_occurrences'], 'verified_occurrences')

    def test_malformed_and_duplicate_grade_name_matches_are_rejected(self):
        for matches in (None, {}, 'invalid', [None]):
            with self.subTest(matches=matches):
                inputs = reviewed_inputs()
                inputs['verified_occurrences']['records'][0]['grade_name_matches'] = matches
                with self.assertRaises(DataError):
                    validate_input(inputs['verified_occurrences'], 'verified_occurrences')
        inputs = reviewed_inputs()
        matches = inputs['verified_occurrences']['records'][0]['grade_name_matches']
        matches.append(deepcopy(matches[0]))
        with self.assertRaisesRegex(DataError, 'duplicate reviewed grade'):
            validate_input(inputs['verified_occurrences'], 'verified_occurrences')

    def test_grade_source_provenance_and_review_time_are_checked(self):
        for mutation, message in (
            ('link_source', 'link provenance'), ('grade_source', 'GPA provenance'),
            ('early_review', 'predates its source'),
        ):
            with self.subTest(mutation=mutation):
                inputs = reviewed_inputs()
                if mutation == 'link_source':
                    inputs['verified_occurrences']['sources'][0]['url'] = 'https://example.org/other'
                elif mutation == 'grade_source':
                    inputs['gpa']['sources'][0]['url'] = 'https://example.org/other'
                else:
                    inputs['gpa']['sources'][0]['fetched_at'] = '2026-01-02T00:00:00Z'
                with self.assertRaisesRegex(DataError, message):
                    attribute(inputs)

    def test_mapping_requires_its_grade_input(self):
        inputs = reviewed_inputs()
        del inputs['gpa']
        with self.assertRaisesRegex(DataError, 'unknown grade'):
            attribute(inputs)

    def test_conflicting_professors_stay_unresolved_and_duplicate_support_does_not_duplicate_grades(self):
        inputs = reviewed_inputs()
        link = deepcopy(inputs['verified_occurrences']['records'][0])
        link['id'] = 'synthetic-second-review'
        inputs['verified_occurrences']['records'].append(link)
        rows = attribute(inputs)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['status'], 'verified')
        person = deepcopy(inputs['professors']['records'][0])
        person['professor_id'] = link['professor_id'] = 'synthetic-different-professor'
        inputs['professors']['records'].append(person)
        self.assertEqual(attribute(inputs)[0]['status'], 'unresolved')

    def test_exact_name_and_reviewed_match_cannot_override_a_conflicting_identity(self):
        inputs = reviewed_inputs()
        grade = inputs['gpa']['records'][0]
        schedule = fixture_snapshot()
        schedule['sections'][0]['meetings'][0]['instructors'][1]['name_raw'] = grade['primary_instructor_name_raw']
        person = deepcopy(inputs['professors']['records'][0])
        person['professor_id'] = 'synthetic-conflicting-person'
        inputs['professors']['records'].append(person)
        link = deepcopy(inputs['verified_occurrences']['records'][0])
        link.update(id='synthetic-exact-name', instructor_index=1, professor_id=person['professor_id'],
                    name_raw=grade['primary_instructor_name_raw'], is_primary=True,
                    primary_evidence=['Synthetic explicit schedule-primary evidence'])
        del link['grade_name_matches']
        inputs['verified_occurrences']['records'].append(link)
        row = attribute_grades(schedule, archive_fixture(current=schedule), inputs)['grade_attributions'][0]
        self.assertEqual(row['status'], 'unresolved')
        self.assertIsNone(row['professor_id'])

    def test_reviewed_match_roundtrips_and_invalid_refresh_keeps_old_publication(self):
        inputs = reviewed_inputs()
        schedule, history = fixture_snapshot(), archive_fixture()
        with tempfile.TemporaryDirectory() as directory:
            publish_bundle(directory, schedule, history, inputs, allow_fixtures=True)
            manifest_path = Path(directory) / 'integration.json'
            original = manifest_path.read_bytes()
            _, documents = validate_bundle(directory)
            self.assertEqual(documents['attributions']['grade_attributions'][0]['status'], 'verified')
            inputs['verified_occurrences']['records'][0]['grade_name_matches'][0]['grade_record_id'] = 'missing'
            with self.assertRaises(DataError):
                publish_bundle(directory, schedule, history, inputs, allow_fixtures=True)
            self.assertEqual(manifest_path.read_bytes(), original)
            validate_bundle(directory)

    def test_committed_reviews_resolve_against_saved_terms_and_keep_other_miles_separate(self):
        inputs = teammate_inputs(read('config/collection.json'))
        links = inputs['verified_occurrences']['records']
        terms = sorted({link['listing_id'].split(':', 1)[0] for link in links})
        snapshots = [load_term('public/data', term) for term in terms]
        history = {'snapshots': snapshots[1:], 'collected_at': snapshots[0]['collected_at']}
        rows = attribute_grades(snapshots[0], history, inputs)['grade_attributions']
        by_id = {row['grade_record_id']: row for row in rows}
        grades_by_id = {grade['id']: grade for grade in inputs['gpa']['records']}
        reviewed = [(link, match) for link in links for match in link.get('grade_name_matches', [])]
        self.assertTrue(reviewed)
        for link, match in reviewed:
            with self.subTest(grade=match['grade_record_id']):
                row = by_id[match['grade_record_id']]
                grade = grades_by_id[match['grade_record_id']]
                self.assertEqual(row['professor_id'], link['professor_id'])
                self.assertEqual(row['section_id'], grade['section_id'] if grade['grain'] == 'section' else None)
        other_miles = [grade for grade in inputs['gpa']['records']
                       if grade.get('primary_instructor_name_raw') == 'Miles, Joshua-Paul M']
        self.assertTrue(other_miles)
        self.assertTrue(all(by_id[grade['id']]['professor_id'] != 'prof_0001' for grade in other_miles))


if __name__ == '__main__':
    unittest.main()
