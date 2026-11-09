"""RMP audit coverage, conservative identity joins, metric provenance and replay."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.data_contract import DataError
from scripts.integration import read, validate_input
from scripts.review_rmp import (API, SCHOOL_ID, SCHOOL_NAME, DirectoryClient, audit,
    collect_directory, context_for, department_matches, export_ratings, identity_fingerprint, metrics, sha, validate_audit)
from tests.fixtures import FIXTURE_TIME


SOURCE = {'url': API, 'request_sha256': 'a' * 64, 'response_sha256': 'b' * 64, 'fetched_at': FIXTURE_TIME}


def node(identifier=1, **changes):
    return {'legacyId': identifier, 'firstName': 'Alexandra', 'lastName': 'Example',
        'department': 'Mathematics', 'school': {'id': SCHOOL_ID, 'name': SCHOOL_NAME},
        'avgRating': 4.5, 'numRatings': 10, 'avgDifficulty': 2.3, 'wouldTakeAgainPercent': 0,
        'courseCodes': [{'courseName': 'MATH101'}], '_source': SOURCE, **changes}


def professors():
    data = read('data/examples/integration/professors.json')
    data['records'][0].update(display_name='Alexandra Example', institutional_id='example', rmp=None)
    return data


def contexts():
    return {'synthetic-alex': {'names': {'Alexandra Example'}, 'units': {'Mathematics, Department of'},
            'courses': {'MATH101'}, 'official_sources': {'https://math.illinois.edu/directory/profile/example'}}}


def ledger(nodes=None, complete=True, people=None, context=None):
    people = people or professors()
    directory = {'complete': complete}
    return {'directory': directory, 'records': audit(people, context or contexts(), nodes or [node()],
             directory, {}, FIXTURE_TIME)}


class RMPReviewTests(unittest.TestCase):
    def test_verified_match_collects_all_metrics_with_provenance_and_genuine_zero(self):
        data = ledger()
        validate_audit(data, professors())
        rating = data['records'][0]['rmp']
        self.assertEqual((rating['overall_quality'], rating['num_ratings'], rating['difficulty'],
                          rating['would_take_again_percent']), (4.5, 10, 2.3, 0))
        self.assertEqual(rating['retrieved_from'], SOURCE)
        self.assertEqual(rating['source_url'], 'https://www.ratemyprofessors.com/professor/1')
        self.assertEqual(rating['scope'], 'professor')

    def test_full_name_requires_department_or_verified_course_context(self):
        data = ledger([node(department='History', courseCodes=[])])
        self.assertEqual(data['records'][0]['status'], 'ambiguous_candidates')
        data = ledger([node(department='History')])
        self.assertEqual(data['records'][0]['status'], 'verified_match')
        self.assertFalse(data['records'][0]['candidates'][0]['department_agrees'])

    def test_only_reviewed_grade_spellings_supplement_an_established_identity(self):
        people = professors()
        people['records'][0].update(display_name='Alex Example', department_names=['Mathematics'])
        source = 'https://example.org/synthetic-grade-source'
        grades = {'sources': [{'url': source}], 'records': [{
            'id': 'synthetic-grade', 'course_code': 'MATH 101',
            'primary_instructor_name_raw': 'Example, Alexandra'}]}
        links = {'records': [{'professor_id': 'synthetic-alex', 'verified': True,
            'listing_id': '2026-fall:MATH 101', 'grade_name_matches': []}]}
        context = context_for(people, {'identities': []}, links, grades)
        self.assertEqual(ledger(context=context, people=people)['records'][0]['status'], 'ambiguous_candidates')
        bridge = {'grade_record_id': 'synthetic-grade',
                  'primary_instructor_name_raw': 'Example, Alexandra', 'source_url': source,
                  'reviewed_by': 'Synthetic identity reviewer', 'verified_at': FIXTURE_TIME,
                  'evidence': ['Individually verified identity spelling'],
                  'primary_evidence': ['Synthetic primary-instructor source field']}
        links['records'][0]['grade_name_matches'] = [bridge]
        context = context_for(people, {'identities': []}, links, grades)
        data = ledger(context=context, people=people)
        self.assertEqual(data['records'][0]['status'], 'verified_match')
        self.assertIn(source, data['records'][0]['rmp']['matching_evidence'][-1])
        self.assertNotIn('Example, Alexandra', data['records'][0]['official_names'])
        self.assertEqual(data['records'][0]['reviewed_grade_names'][0]['grade_record_id'], 'synthetic-grade')
        bridge['primary_instructor_name_raw'] = 'Example, Somebody Else'
        with self.assertRaises(DataError):
            context_for(people, {'identities': []}, links, grades)

    def test_department_label_aliases_preserve_exact_names_and_do_not_merge_adjacent_fields(self):
        aliases = {'Computer Science': 'Siebel School of Computing and Data Science'}
        self.assertTrue(department_matches('Computer Science', {'Computer Science, Department of'}, aliases))
        self.assertTrue(department_matches('Computer Science', {'Siebel School of Computing and Data Science'}, aliases))
        self.assertFalse(department_matches('Psychology', {'Educational Psychology'}, aliases))
        self.assertTrue(department_matches('Classics', {'Classics, Department of the'}, {}))

    def test_reviewed_college_context_keeps_name_checks_and_duplicate_profile_ambiguity(self):
        context = contexts()
        context['synthetic-alex']['units'] = {'Electrical and Computer Engineering'}
        context['synthetic-alex']['courses'] = set()
        review = {'official_units': ['Electrical and Computer Engineering'],
                  'reviewed_by': 'Synthetic reviewer', 'reviewed_at': FIXTURE_TIME,
                  'evidence': 'Synthetic college hierarchy evidence',
                  'sources': [{'url': 'https://catalog.illinois.edu/synthetic',
                               'fetched_at': FIXTURE_TIME, 'sha256': 'c' * 64}]}
        config = {'department_aliases': {'Engineering': review['official_units']},
                  'department_alias_reviews': {'Engineering': review}}
        directory = {'complete': True}
        rows = audit(professors(), context, [node(department='Engineering', courseCodes=[])], directory, config, FIXTURE_TIME)
        self.assertEqual(rows[0]['status'], 'verified_match')
        self.assertEqual(rows[0]['candidates'][0]['department_alias_review'], review)
        self.assertIn('https://catalog.illinois.edu/synthetic', rows[0]['rmp']['matching_evidence'][-1])
        rows = audit(professors(), context, [node(firstName='Alex', department='Engineering')], directory, config, FIXTURE_TIME)
        self.assertEqual(rows[0]['status'], 'ambiguous_candidates')
        rows = audit(professors(), context, [node(department='Engineering'), node(2, department='Engineering')], directory, config, FIXTURE_TIME)
        self.assertEqual(rows[0]['reason'], 'multiple_supported_profiles')
        config['department_aliases']['Engineering'] = ['Unrelated unit']
        context['synthetic-alex']['units'] = {'Unrelated unit'}
        with self.assertRaises(DataError):
            audit(professors(), context, [node(department='Engineering')], directory, config, FIXTURE_TIME)

    def test_initial_nickname_and_conflicting_middle_names_are_never_automatic_matches(self):
        for first in ('A', 'Alex', 'Alexandra R'):
            context = contexts()
            context['synthetic-alex']['names'] = {'Example, Alexandra Q'}
            with self.subTest(first=first):
                entry = ledger([node(firstName=first)], context=context)['records'][0]
                self.assertEqual(entry['status'], 'ambiguous_candidates')
                self.assertIsNone(entry['rmp'])

    def test_explicit_parenthetical_prefix_nickname_does_not_become_a_middle_name(self):
        data = ledger([node(firstName='Alexandra (Alex)')])
        self.assertEqual(data['records'][0]['status'], 'verified_match')
        self.assertEqual(data['records'][0]['candidates'][0]['name'], 'Example, Alexandra (Alex)')
        self.assertEqual(data['records'][0]['candidates'][0]['matching_name'], 'Example, Alexandra')
        whitespace = ledger([node(firstName='Alexandra ')])
        self.assertNotIn('matching_name', whitespace['records'][0]['candidates'][0])
        context = contexts()
        context['synthetic-alex']['names'] = {'Example, Alexandra Q'}
        data = ledger([node(firstName='Alexandra R (Alex)')], context=context)
        self.assertEqual(data['records'][0]['status'], 'ambiguous_candidates')
        data = ledger([node(firstName='Alex')])
        self.assertEqual(data['records'][0]['status'], 'ambiguous_candidates')

    def test_shortened_compound_surname_is_a_candidate_requiring_review(self):
        context = contexts()
        context['synthetic-alex']['names'] = {'Alexandra Example-Other'}
        entry = ledger(context=context)['records'][0]
        self.assertEqual(entry['status'], 'ambiguous_candidates')
        self.assertEqual(len(entry['candidates']), 1)

    def test_multiple_supported_profiles_and_shared_profile_ownership_stay_ambiguous(self):
        entry = ledger([node(), node(2)])['records'][0]
        self.assertEqual(entry['reason'], 'multiple_supported_profiles')
        people, context = professors(), contexts()
        second = deepcopy(people['records'][0])
        second['professor_id'] = 'synthetic-other'
        people['records'].append(second)
        context['synthetic-other'] = deepcopy(context['synthetic-alex'])
        data = ledger(people=people, context=context)
        self.assertTrue(all(e['reason'] == 'profile_shared_by_multiple_guide_identities' for e in data['records']))

    def test_incomplete_directory_is_unavailable_even_when_one_candidate_looks_valid(self):
        data = ledger(complete=False)
        self.assertEqual(data['records'][0]['status'], 'lookup_unavailable')
        self.assertIsNone(data['records'][0]['rmp'])
        directory = {'complete': True}
        entries = audit(professors(), contexts(), [], directory, {}, FIXTURE_TIME)
        self.assertEqual(entries[0]['status'], 'no_matching_profile_found')

    def test_missing_metrics_and_source_sentinels_are_unavailable(self):
        values = metrics(node(avgRating=0, avgDifficulty=0, wouldTakeAgainPercent=-1, numRatings=0))
        self.assertEqual(values, {'num_ratings': 0, 'overall_quality': None, 'difficulty': None,
                                  'would_take_again_percent': None})
        self.assertIsNone(metrics(node(avgDifficulty=None))['difficulty'])
        for changes in ({'numRatings': -1}, {'avgRating': 5.1}, {'avgDifficulty': float('nan')},
                        {'wouldTakeAgainPercent': 101}, {'avgRating': True}):
            with self.subTest(changes=changes), self.assertRaises(DataError):
                metrics(node(**changes))

    def test_audit_requires_every_identity_once_and_accepted_rating_provenance(self):
        data = ledger()
        for mutation in ('missing_record', 'duplicate_record', 'missing_source', 'wrong_metric'):
            broken = deepcopy(data)
            if mutation == 'missing_record':
                broken['records'] = []
            elif mutation == 'duplicate_record':
                broken['records'] *= 2
            elif mutation == 'missing_source':
                broken['records'][0]['rmp']['retrieved_from'] = {**SOURCE, 'response_sha256': ''}
            else:
                broken['records'][0]['rmp']['overall_quality'] = 1
            with self.subTest(mutation=mutation), self.assertRaises(DataError):
                validate_audit(broken, professors())

    def test_export_preserves_instructor_set_and_rebuilds_prior_batch_ratings(self):
        original, data = professors(), ledger()
        updated = export_ratings(original, data)
        self.assertEqual(identity_fingerprint(original), identity_fingerprint(updated))
        self.assertIsNone(original['records'][0]['rmp'])
        self.assertEqual(export_ratings(updated, data), updated)
        data['records'][0].update(status='ambiguous_candidates', rmp=None)
        self.assertIsNone(export_ratings(updated, data)['records'][0]['rmp'])

    def test_new_metric_bounds_are_validated_and_legacy_ratings_remain_valid(self):
        data = read('data/examples/integration/professors.json')
        validate_input(data, 'professors')
        for key, value in [('difficulty', -1), ('difficulty', 5.1), ('difficulty', True),
                           ('would_take_again_percent', -1), ('would_take_again_percent', 101)]:
            changed = deepcopy(data)
            changed['records'][0]['rmp'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(DataError):
                validate_input(changed, 'professors')
        data['records'][0]['rmp'].update(difficulty=None, would_take_again_percent=0)
        validate_input(data, 'professors')

    def test_verified_teaching_links_provide_context_without_needing_gpa(self):
        people = professors()
        gpa = read('data/examples/integration/gpa.json')
        links = read('data/examples/integration/verified-links.json')
        result = context_for(people, {'identities': []}, links, gpa)
        self.assertEqual(result['synthetic-alex']['courses'], {'CS374'})
        links['records'][0]['verified'] = False
        result = context_for(people, {'identities': []}, links, gpa)
        self.assertEqual(result['synthetic-alex']['courses'], set())

    def test_complete_pagination_rejects_duplicates_wrong_school_fallback_and_missing_rows(self):
        class Client:
            def __init__(self, pages): self.pages = iter(pages)
            def page(self, cursor): return next(self.pages)
        def page(items, more=False, cursor='end', count=2):
            return {**SOURCE, 'data': {'resultCount': count, 'didFallback': False,
                'edges': [{'node': x} for x in items], 'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}}
        nodes, coverage = collect_directory(Client([page([node()], True), page([node(2)])]))
        self.assertTrue(coverage['complete'])
        self.assertEqual(len(nodes), 2)
        nodes, coverage = collect_directory(Client([page([node()], True), page([node()])]))
        self.assertTrue(coverage['complete'])
        self.assertEqual(coverage['duplicate_profile_ids'], [1])
        self.assertEqual(len(nodes), 1)
        for pages in ([page([node()], True), page([node(lastName='Conflicting')])], [page([node()])],
                      [page([node(school={'id': 'other', 'name': SCHOOL_NAME})])],
                      [{**page([node()]), 'data': {**page([node()])['data'], 'didFallback': True}}]):
            with self.subTest(pages=pages):
                _, coverage = collect_directory(Client(pages))
                self.assertFalse(coverage['complete'])
                self.assertTrue(coverage['failures'])

    def test_http_access_denial_stops_requests_across_runs(self):
        response = subprocess.CompletedProcess([], 0, b'Blocked\n403', b'')
        with tempfile.TemporaryDirectory() as directory:
            with patch('scripts.review_rmp.subprocess.run', return_value=response) as request:
                with self.assertRaisesRegex(DataError, 'HTTP 403'):
                    DirectoryClient(directory, pace=0).page('')
                with self.assertRaisesRegex(DataError, 'access deferred'):
                    DirectoryClient(directory, pace=0).page('next')
                self.assertEqual(request.call_count, 1)

    def test_saved_source_replays_offline_and_detects_modified_response(self):
        data = {'edges': [], 'pageInfo': {'hasNextPage': False, 'endCursor': None},
                'resultCount': 0, 'didFallback': False}
        raw = json.dumps({'data': {'search': {'teachers': data}}}).encode()
        response = subprocess.CompletedProcess([], 0, raw + b'\n200', b'')
        with tempfile.TemporaryDirectory() as directory:
            with patch('scripts.review_rmp.subprocess.run', return_value=response):
                saved = DirectoryClient(directory, pace=0).page('')
            with patch('scripts.review_rmp.subprocess.run', side_effect=AssertionError('Unexpected network')):
                self.assertEqual(DirectoryClient(directory, offline=True).page(''), saved)
                path = next(Path(directory).glob('*.json'))
                altered = json.loads(path.read_text())
                altered['data']['resultCount'] = 1
                path.write_text(json.dumps(altered))
                with self.assertRaisesRegex(DataError, 'cache integrity'):
                    DirectoryClient(directory, offline=True).page('')


if __name__ == '__main__':
    unittest.main()
