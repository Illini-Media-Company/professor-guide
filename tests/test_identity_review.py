"""Offline checks for directory-backed identity review and cautious exports."""

from copy import deepcopy
import base64
import subprocess
import tempfile
import unittest
import json
from unittest.mock import patch

from scripts.data_contract import DataError
from scripts.integration import read, validate_input
from scripts.review_identities import (DirectoryParser, FacultyProfile, FacultyProfileIndex, GraingerDirectory,
    SourceCache, collect_directories, export_reviews, api_people, digest, full_name_agrees,
    minimize_directory_payload, review_archive_names, review_inventory,
    schedule_name_agrees, unit_agrees, validate_review_inventory)
from tests.fixtures import FIXTURE_TIME


URL = 'https://math.illinois.edu/directory'
CONFIG = {'subject_units': {'MATH': ['Mathematics'], 'PSYC': ['Psychology, Department']}}


def person(netid='example', name='Example, Alexandra Q', unit='Mathematics, Department of'):
    return {'netid': netid, 'name': name, 'unit': unit, 'unit_url': URL,
            'source_url': URL, 'profile_url': None}


def data():
    gpa = read('data/examples/integration/gpa.json')
    gpa['records'] = [gpa['records'][0]]
    gpa['records'][0].update(course_code='MATH 101', primary_instructor_name_raw='Example, Alexandra Q')
    occurrence = {'listing_id': '2026-fall:MATH 101', 'section_id': '2026-fall:10001',
        'meeting_id': '2026-fall:10001:0', 'instructor_index': 0, 'name_raw': 'Example, A',
        'source_url': 'https://courses.illinois.edu/synthetic-fixture', 'fetched_at': FIXTURE_TIME}
    return gpa, {occurrence['listing_id']: [occurrence]}


def review(people):
    gpa, listings = data()
    return review_inventory(gpa['records'], people, listings, CONFIG, FIXTURE_TIME)


class IdentityReviewTests(unittest.TestCase):
    def test_complete_first_and_last_names_with_compatible_middle_names(self):
        for left, right in (
            ('Example, Alexandra Q', 'Example, Alexandra'),
            ('Example, Alexandra Q', 'Alexandra Quinn Example'),
            ('García, José A', 'Jose Antonio Garcia'),
            ('Chica Duque, Felipe', 'Felipe Chica Duque'),
        ):
            with self.subTest(left=left, right=right):
                self.assertTrue(full_name_agrees(left, right))
        for left, right in (
            ('Example, A', 'Alexandra Example'),
            ('Example, Alexandra Q', 'Alexandra R Example'),
            ('Example, Alexandra', 'Alex Example'),
            ('Fagen-Ulmschnei, Wade A', 'Fagen-Ulmschneider, Wade A'),
        ):
            with self.subTest(left=left, right=right):
                self.assertFalse(full_name_agrees(left, right))

    def test_schedule_initials_do_not_equate_different_full_first_names(self):
        self.assertTrue(schedule_name_agrees('Example, Alexandra', 'Example, A'))
        self.assertFalse(schedule_name_agrees('Example, Alexandra', 'Example, Alice'))

    def test_department_scope_does_not_confuse_psychology_and_educational_psychology(self):
        self.assertFalse(unit_agrees('PSYC', person(unit='Educational Psychology, Department of'), CONFIG))
        self.assertEqual(review([person(unit='Physics, Department of')])[0]['status'], 'needs_review')

    def test_public_college_api_preserves_academic_scope_and_requires_all_pages(self):
        spec = {'kind': 'wigg_search', 'url': URL, 'unit': 'Education, College of',
                'directory_url': URL, 'subjects': ['EDUC', 'CI', 'EPSY']}
        payload = {'count': 1, 'people': [{'netId': 'example', 'fullNameReversed': 'Example, Alexandra',
                    'jobProfiles': [{'office': 'Finance'}], 'published': True}]}
        parsed = api_people(payload, spec)
        finance = {'subject_units': {'FIN': ['Finance, Department']}}
        self.assertTrue(parsed)
        self.assertTrue(all(not unit_agrees('FIN', p, finance) for p in parsed))
        payload['count'] = 2
        with self.assertRaisesRegex(DataError, 'Incomplete'):
            api_people(payload, spec)
        payload['count'] = 1
        payload['people'][0]['published'] = False
        self.assertEqual(api_people(payload, spec), [])

    def test_api_cache_retains_identity_fields_and_discards_unneeded_personal_fields(self):
        payload = {'count': 1, 'people': [{'netId': 'example', 'fullName': 'Alexandra Example',
                    'uin': 'synthetic-student-number', 'phone': 'synthetic-phone',
                    'address': 'synthetic-address', 'email': 'synthetic-email',
                    'jobProfiles': [{'office': 'Mathematics', 'title': 'Lecturer'}]}]}
        minimized = minimize_directory_payload(payload)
        text = json.dumps(minimized)
        for omitted in ('synthetic-student-number', 'synthetic-phone', 'synthetic-address', 'synthetic-email'):
            self.assertNotIn(omitted, text)
        self.assertEqual(minimized['people'][0]['netId'], 'example')
        self.assertEqual(minimized['people'][0]['jobProfiles'][0]['office'], 'Mathematics')

    def test_unique_full_name_department_and_occurrence_yield_scoped_review(self):
        row = review([person()])[0]
        self.assertEqual(row['status'], 'verified_identity')
        self.assertEqual(row['netid'], 'example')
        self.assertEqual(len(row['matched_grades']), 1)
        self.assertEqual(row['matched_grades'][0]['occurrence']['name_raw'], 'Example, A')

    def test_multiple_official_ids_are_not_merged_by_name(self):
        row = review([person(), person(netid='example2')])[0]
        self.assertEqual(row['status'], 'needs_review')
        self.assertEqual(row['reason'], 'multiple_official_identities')
        self.assertEqual(row['matched_grades'], [])

    def test_multiple_sources_for_same_official_id_do_not_create_two_people(self):
        second = person()
        second['source_url'] = 'https://math.illinois.edu/directory/faculty'
        row = review([person(), second])[0]
        self.assertEqual(row['status'], 'verified_identity')
        self.assertEqual(len(row['candidates']), 1)
        self.assertEqual(len(row['candidates'][0]['source_urls']), 2)

    def test_same_initial_collision_keeps_grade_unresolved_despite_known_full_identity(self):
        row = review([person(), person(netid='alice', name='Example, Alice')])[0]
        self.assertEqual(row['status'], 'verified_identity')
        self.assertEqual(row['matched_grades'], [])
        self.assertEqual(row['unresolved_grades'][0]['reason'], 'ambiguous_schedule_initials')

    def test_historical_grade_names_also_block_ambiguous_schedule_initials(self):
        gpa, listings = data()
        another = deepcopy(gpa['records'][0])
        another.update(id='synthetic-former-instructor', primary_instructor_name_raw='Example, Alice')
        gpa['records'].append(another)
        reviews = review_inventory(gpa['records'], [person()], listings, CONFIG, FIXTURE_TIME)
        reviewed = next(row for row in reviews if row['grade_name_raw'] == 'Example, Alexandra Q')
        self.assertEqual(reviewed['status'], 'verified_identity')
        self.assertEqual(reviewed['matched_grades'], [])
        self.assertEqual(reviewed['unresolved_grades'][0]['reason'], 'ambiguous_grade_source_names')

    def test_missing_directory_middle_name_does_not_merge_conflicting_grade_names(self):
        gpa, listings = data()
        second = deepcopy(gpa['records'][0])
        second.update(id='synthetic-conflicting-middle', primary_instructor_name_raw='Example, Alexandra R')
        gpa['records'].append(second)
        reviews = review_inventory(gpa['records'], [person(name='Example, Alexandra')], listings, CONFIG, FIXTURE_TIME)
        self.assertTrue(all(row['reason'] == 'conflicting_names_for_official_identity' for row in reviews))
        self.assertTrue(all(not row['matched_grades'] for row in reviews))

    def test_every_source_label_and_grade_row_requires_exactly_one_outcome(self):
        gpa, _ = data()
        reviews = review([person()])
        validate_review_inventory(gpa['records'], reviews)
        for invalid in ([], reviews + deepcopy(reviews)):
            with self.subTest(invalid=invalid), self.assertRaises(DataError):
                validate_review_inventory(gpa['records'], invalid)
        invalid = deepcopy(reviews)
        invalid[0]['matched_grades'][0]['grade_record_id'] = 'synthetic-missing'
        with self.assertRaises(DataError):
            validate_review_inventory(gpa['records'], invalid)

    def test_reviewed_name_variant_is_literal_and_requires_recorded_evidence(self):
        gpa, listings = data()
        gpa['records'][0]['primary_instructor_name_raw'] = 'Example, Alex Q'
        config = deepcopy(CONFIG)
        config['reviewed_name_variants'] = [{
            'grade_name_raw': 'Example, Alex Q', 'directory_id': 'example',
            'official_name': 'Example, Alexandra Q', 'reviewed_by': 'Synthetic reviewer',
            'reviewed_at': FIXTURE_TIME, 'source_urls': [URL],
            'evidence': ['Synthetic course document explicitly connects these two spellings.']}]
        rows = review_inventory(gpa['records'], [person()], listings, config, FIXTURE_TIME)
        self.assertEqual(rows[0]['reason'], 'reviewed_source_name_variant')
        self.assertEqual(len(rows[0]['matched_grades']), 1)
        gpa['records'][0]['primary_instructor_name_raw'] = 'Example, Alexis Q'
        rows = review_inventory(gpa['records'], [person()], listings, config, FIXTURE_TIME)
        self.assertEqual(rows[0]['status'], 'needs_review')
        gpa['records'][0]['primary_instructor_name_raw'] = 'Example, Alex Q'
        config['reviewed_name_variants'][0]['evidence'] = []
        with self.assertRaises(DataError):
            review_inventory(gpa['records'], [person()], listings, config, FIXTURE_TIME)

    def test_rebuilt_batch_removes_decisions_when_new_evidence_makes_them_ambiguous(self):
        gpa, _ = data()
        ledger = {'identities': review([person()]), 'reviewed_at': FIXTURE_TIME,
                  'sources': {URL: {'fetched_at': FIXTURE_TIME}}}
        professors = read('data/examples/integration/professors.json')
        links = read('data/examples/integration/verified-links.json')
        links['records'][0].update(section_id='2026-fall:10009', meeting_id='2026-fall:10009:0')
        professors, links = export_reviews(ledger, gpa, professors, links)
        self.assertEqual(len(links['records']), 2)
        ledger['identities'][0]['matched_grades'] = []
        _, links = export_reviews(ledger, gpa, professors, links)
        self.assertEqual(len(links['records']), 1)
        self.assertEqual(links['records'][0]['id'], 'synthetic-occurrence')

    def test_missing_schedule_and_different_subject_do_not_gain_attribution(self):
        gpa, _ = data()
        row = review_inventory(gpa['records'], [person()], {}, CONFIG, FIXTURE_TIME)[0]
        self.assertEqual(row['matched_grades'], [])
        self.assertEqual(row['unresolved_grades'][0]['reason'], 'no_matching_schedule_occurrence')

    def test_export_is_idempotent_and_preserves_existing_professor_id(self):
        gpa, _ = data()
        identities = review([person()])
        professors = read('data/examples/integration/professors.json')
        professors['records'][0]['faculty_links'] = [{
            'url': 'https://math.illinois.edu/directory/profile/example',
            'evidence': 'Synthetic identity', 'verified_at': FIXTURE_TIME}]
        links = read('data/examples/integration/verified-links.json')
        links['records'][0].update(section_id='2026-fall:10009', meeting_id='2026-fall:10009:0')
        ledger = {'identities': identities, 'reviewed_at': FIXTURE_TIME,
                  'sources': {URL: {'fetched_at': FIXTURE_TIME}}}
        exported_people, exported_links = export_reviews(ledger, gpa, professors, links)
        self.assertEqual(len(exported_people['records']), 1)
        new_link = exported_links['records'][-1]
        self.assertEqual(new_link['professor_id'], 'synthetic-alex')
        self.assertFalse(new_link['is_primary'])
        self.assertEqual(new_link['grade_name_matches'][0]['grade_record_id'], 'synthetic-zero')
        before = deepcopy((exported_people, exported_links))
        self.assertEqual(export_reviews(ledger, gpa, exported_people, exported_links), before)
        validate_input(exported_people, 'professors')
        validate_input(exported_links, 'verified_occurrences')

    def test_parser_retains_department_context_and_profile_names_without_a_css_dependency(self):
        parser = DirectoryParser('https://directory.illinois.edu/facultyListing')
        parser.feed('''<h3><a href="/detail?departmentId=math">Mathematics</a></h3>
          <li><a href="/search?search_type=userid&amp;netID=example@illinois.edu">Example, Alexandra</a></li>
          <h3><a href="/detail?departmentId=physics">Physics</a></h3>
          <li><a href="javascript:goToDetail('other')">Other, Olivia</a></li>''')
        self.assertEqual([(p['netid'], p['unit']) for p in parser.people],
                         [('example', 'Mathematics'), ('other', 'Physics')])
        parser = DirectoryParser(URL, 'Mathematics')
        parser.feed('<a href="/profile/example">Alexandra Example</a><a href="/directory/profile/other">Olivia Other</a>')
        self.assertEqual(len(parser.people), 2)
        self.assertEqual(parser.people[0]['profile_url'], 'https://math.illinois.edu/profile/example')

    def test_ischool_roster_binds_each_profile_to_its_published_netid(self):
        parser = DirectoryParser('https://ischool.illinois.edu/people/directory', 'Information Sciences')
        parser.feed('''<div class="directory-row"><a class="directory-row__link" href="/people/alexandra-example">Example, Alexandra</a>
          <a href="mailto:example@illinois.edu">Contact</a></div>
          <div class="directory-row"><a class="directory-row__link" href="/people/olivia-other">Other, Olivia</a>
          <a href="mailto:not-a-university-id@example.org">Contact</a></div>''')
        self.assertEqual(len(parser.people), 1)
        self.assertEqual(parser.people[0]['netid'], 'example')
        self.assertEqual(parser.people[0]['name'], 'Example, Alexandra')

    def test_unlinked_staff_card_requires_its_own_published_university_identifier(self):
        parser = DirectoryParser(URL, 'Mathematics')
        parser.feed('''<article class="profile-card">
          <div class="field-dircore-display-name"><div>Alexandra Example</div></div>
          <div><a href="mailto:example@illinois.edu">Contact</a></div></article>
          <article class="profile-card"><div class="field-dircore-display-name">Olivia Other</div></article>
          <footer><a href="mailto:unrelated@illinois.edu">Office</a></footer>''')
        self.assertEqual([(p['netid'], p['name']) for p in parser.people], [('example', 'Alexandra Example')])

    def test_faculty_profile_index_requires_its_own_host_and_profile_path(self):
        spec = {'url': 'https://law.illinois.edu/faculty/', 'profile_prefix': '/faculty/profiles/'}
        index = FacultyProfileIndex(spec)
        index.feed('''<a href="/faculty/profiles/alexandra">Alexandra Example</a>
          <a href="https://example.org/faculty/profiles/other">Olivia Other</a>
          <a href="/faculty/profiles/">All profiles</a>
          <a href="/news/olivia">Olivia Other</a>''')
        self.assertEqual(index.profiles, {'https://law.illinois.edu/faculty/profiles/alexandra': 'Alexandra Example'})

    def test_engineering_cards_keep_each_name_identifier_and_department_together(self):
        spec = {'url': 'https://grainger.illinois.edu/about/directory/faculty', 'units': {'math': 'Mathematics'}}
        parser = GraingerDirectory(spec)
        parser.feed('''<div class="person" data-netid="example" data-dept="math">
          <div><a href="/about/directory/faculty/example">Alexandra Example</a></div></div>
          <div class="person" data-netid="unrecognized" data-dept="unknown">
          <a href="/about/directory/faculty/unrecognized">Olivia Other</a></div>''')
        self.assertEqual([(p['netid'], p['name'], p['unit']) for p in parser.people],
                         [('example', 'Alexandra Example', 'Mathematics')])

    def test_faculty_profile_binds_own_contact_and_excludes_assistants_and_footer(self):
        profile = FacultyProfile()
        profile.feed('''<main><h2>Alexandra Example</h2><h3>Contact</h3>
          <a href="mailto:example@illinois.edu">Contact Alexandra</a>
          <h4>Assistant</h4><a href="mailto:assistant@illinois.edu">Assistant</a>
          </main><footer><a href="mailto:office@illinois.edu">Office</a></footer>''')
        self.assertEqual(profile.names, ['Alexandra Example'])
        self.assertEqual(profile.netids, {'example'})

    def test_arts_profile_uses_its_contact_card_without_capturing_other_addresses(self):
        profile = FacultyProfile()
        profile.feed('''<main><h1>Alexandra Example</h1>
          <div class="profile-primary-info__contact-email"><a href="mailto:example@illinois.edu">Email</a></div>
          <div><a href="mailto:assistant@illinois.edu">Assistant</a></div></main>''')
        self.assertEqual(profile.netids, {'example'})

    def test_profile_collection_follows_directory_pagination_before_matching_names(self):
        root = 'https://art.illinois.edu/about/faculty/'
        page = root + 'page/2/'
        first = 'https://art.illinois.edu/people/profiles/alexandra/'
        second = 'https://art.illinois.edu/people/profiles/olivia/'
        bodies = {
            'https://directory.illinois.edu/facultyListing': '',
            'https://directory.illinois.edu/departmentsUnits': '',
            root: f'<a href="{first}">Alexandra Example</a><a href="{page}">2</a>',
            page: f'<a href="{second}">Olivia Other</a><a href="{root}">1</a>',
            first: '<main><h1>Alexandra Example</h1><h2>Contact</h2><a href="mailto:example@illinois.edu">Email</a></main>',
            second: '<main><h1>Olivia Other</h1><h2>Contact</h2><a href="mailto:other@illinois.edu">Email</a></main>',
        }
        config = {'subject_units': {}, '_grade_names': ['Example, Alexandra', 'Other, Olivia'],
                  'profile_indexes': [{'url': root, 'profile_prefix': '/people/profiles/',
                    'page_prefix': '/about/faculty/page/', 'unit': 'Art and Design', 'subjects': ['ART']} ]}
        with tempfile.TemporaryDirectory() as directory:
            cache = SourceCache(directory, offline=True)
            with patch.object(cache, 'fetch', side_effect=lambda url: {
                    'url': url, 'fetched_at': FIXTURE_TIME, 'body': bodies[url], 'sha256': digest(bodies[url].encode())}):
                people, sources, failures = collect_directories(cache, config)
        self.assertFalse(failures)
        self.assertIn(page, sources)
        self.assertEqual({p['netid'] for p in people}, {'example', 'other'})

    def test_profile_uri_identity_exports_without_fabricating_an_institutional_id(self):
        profile_url = 'https://law.illinois.edu/faculty/profiles/alexandra/'
        identifier = 'profile_' + digest(profile_url.encode())[:24]
        official = person(netid=identifier)
        official['profile_url'] = profile_url
        gpa, _ = data()
        ledger = {'identities': review([official]), 'reviewed_at': FIXTURE_TIME,
                  'sources': {URL: {'fetched_at': FIXTURE_TIME}}}
        professors = read('data/examples/integration/professors.json')
        professors['records'] = []
        links = read('data/examples/integration/verified-links.json')
        links['records'] = []
        professors, links = export_reviews(ledger, gpa, professors, links)
        self.assertEqual(professors['records'][0]['directory_profile_url'], profile_url)
        self.assertNotIn('institutional_id', professors['records'][0])
        expected = deepcopy((professors, links))
        self.assertEqual(export_reviews(ledger, gpa, professors, links), expected)

    def test_binary_source_cache_checks_original_pdf_bytes(self):
        url = 'https://math.illinois.edu/syllabus.pdf'
        body = b'%PDF-1.5\n\xff synthetic evidence'
        with tempfile.TemporaryDirectory() as root:
            cache = SourceCache(root, offline=True)
            saved = {'url': url, 'fetched_at': FIXTURE_TIME, 'sha256': digest(body),
                     'body': base64.b64encode(body).decode(), 'body_encoding': 'base64'}
            cache.path(url).write_text(json.dumps(saved))
            self.assertEqual(cache.fetch(url), saved)
            saved['body'] = base64.b64encode(body + b' changed').decode()
            cache.path(url).write_text(json.dumps(saved))
            with self.assertRaisesRegex(DataError, 'hash mismatch'):
                cache.fetch(url)

    def test_initials_only_archive_candidate_is_retained_for_further_occurrence_review(self):
        _, listings = data()
        occurrence = listings['2026-fall:MATH 101'][0]
        archive = {('MATH', 'Example, A'): [occurrence]}
        reviews = review_archive_names(archive, [person()], CONFIG, [], {'records': []})
        self.assertEqual(reviews[0]['status'], 'candidate_requires_occurrence_review')
        self.assertEqual(reviews[0]['review_scope'], 'archive_only_label')
        reviews = review_archive_names(archive, [person()], CONFIG, review([person()]), {'records': []})
        self.assertEqual(reviews[0]['review_scope'], 'gpa_context')
        self.assertEqual(reviews[0]['gpa_source_name_candidates'], ['Example, Alexandra Q'])
        self.assertEqual(reviews[0]['verified_occurrence_count'], 0)
        link = {**occurrence, 'verified': True}
        reviews = review_archive_names(archive, [person()], CONFIG, [], {'records': [link]})
        self.assertEqual(reviews[0]['status'], 'verified_occurrences')
        link['name_raw'] = 'Wrong, Person'
        reviews = review_archive_names(archive, [person()], CONFIG, [], {'records': [link]})
        self.assertEqual(reviews[0]['status'], 'candidate_requires_occurrence_review')

    def test_access_denial_defers_host_across_runs_instead_of_retrying_or_recording_absence(self):
        response = subprocess.CompletedProcess([], 0, b'Denied\n403\nhttps://math.illinois.edu/directory', b'')
        with tempfile.TemporaryDirectory() as root:
            with patch('scripts.review_identities.subprocess.run', return_value=response) as request:
                with self.assertRaisesRegex(DataError, 'access deferred'):
                    SourceCache(root, pace=0).fetch(URL)
                with self.assertRaisesRegex(DataError, 'host deferred'):
                    SourceCache(root, pace=0).fetch('https://math.illinois.edu/directory/faculty')
                self.assertEqual(request.call_count, 1)

    def test_cached_http_200_directory_unavailable_is_not_an_empty_roster(self):
        body = '<html><title>Directory Unavailable</title><h1>Directory Unavailable</h1></html>'
        with tempfile.TemporaryDirectory() as root:
            cache = SourceCache(root, offline=True)
            cache.path(URL).write_text(json.dumps({'url': URL, 'body': body,
                'sha256': digest(body.encode()), 'fetched_at': FIXTURE_TIME}))
            with self.assertRaisesRegex(DataError, 'access-denied, not an empty directory'):
                cache.fetch(URL)


if __name__ == '__main__':
    unittest.main()
