from copy import deepcopy
import unittest

from scripts.import_faculty import merge_faculty
from scripts.integration import read
from scripts.review_rmp import context_for
from tests.fixtures import FIXTURE_TIME


URL = 'https://grainger.illinois.edu/about/directory/faculty'
SOURCES = {URL: {'url': URL, 'fetched_at': FIXTURE_TIME, 'sha256': 'a' * 64}}


def row(netid='newfaculty', name='New Faculty'):
    return {'netid': netid, 'name': name, 'unit': 'Mathematics', 'source_url': URL,
            'profile_url': 'https://math.illinois.edu/directory/profile/' + netid}


class FacultyImportTests(unittest.TestCase):
    def test_directory_faculty_are_included_without_any_gpa_or_course_links(self):
        original = read('data/examples/integration/professors.json')
        output, report = merge_faculty(original, [row(), row()], SOURCES, FIXTURE_TIME)
        self.assertEqual(len(output['records']), len(original['records']) + 1)
        added = output['records'][-1]
        self.assertEqual(added['institutional_id'], 'newfaculty')
        self.assertIsNone(added['rmp'])
        self.assertNotIn('courses', added)
        self.assertEqual(added['department_names'], ['Mathematics'])
        self.assertEqual(report['added_professor_ids'], ['prof_uiuc_newfaculty'])

    def test_existing_institutional_identity_and_ratings_are_preserved(self):
        original = read('data/examples/integration/professors.json')
        original['records'][0]['institutional_id'] = 'existing'
        before = deepcopy(original['records'])
        output, report = merge_faculty(original, [row('existing', 'Another Official Spelling')], SOURCES, FIXTURE_TIME)
        self.assertEqual(output['records'], before)
        self.assertEqual(report['added_professor_ids'], [])

    def test_same_name_with_an_unreconciled_profile_uri_is_held_without_merging_ids(self):
        original = read('data/examples/integration/professors.json')
        original['records'][0].update(display_name='Alex Example', directory_profile_url='https://law.illinois.edu/faculty/alex/')
        output, report = merge_faculty(original, [row(name='Example, Alex')], SOURCES, FIXTURE_TIME)
        self.assertEqual(len(output['records']), len(original['records']))
        self.assertEqual(len(report['held_for_reconciliation']), 1)

    def test_official_directory_names_and_units_support_rmp_without_gpa(self):
        original = read('data/examples/integration/professors.json')
        output, _ = merge_faculty(original, [row()], SOURCES, FIXTURE_TIME)
        contexts = context_for(output, {'identities': []}, {'records': []}, {'records': []})
        context = contexts['prof_uiuc_newfaculty']
        self.assertEqual(context['units'], {'Mathematics'})
        self.assertEqual(context['courses'], set())
        self.assertIn('New Faculty', context['names'])


if __name__ == '__main__':
    unittest.main()
