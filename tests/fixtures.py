"""Small synthetic responses shared by tests of the production collection path."""

from copy import deepcopy
from pathlib import Path
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from scripts.archive import requested_terms, totals, validate_archive
from scripts.collect_campus import department_snapshot, merge_departments, subjects_for
from scripts.course_explorer_discovery import CourseExplorerDiscovery, parse_xml
from scripts.data_contract import counts

FIXTURES = Path(__file__).resolve().parents[1] / 'data/examples/course-explorer-xml'
FIXTURE_TIME = '2026-01-01T00:00:00Z'


class FixtureClient:
    def fetch(self, url, expected_root='course', **kwargs):
        path = urlsplit(url).path
        discovery_dir = FIXTURES.parent / 'discovery-xml'
        if expected_root == 'schedule':
            file = discovery_dir / 'schedule.xml'
        elif expected_root == 'calendarYear':
            file = discovery_dir / ('year-' + path.rsplit('/', 1)[-1])
        elif expected_root == 'term':
            file = discovery_dir / 'term.xml'
        elif expected_root == 'subject':
            file = discovery_dir / ('subject-' + path.rsplit('/', 1)[-1].lower())
        else:
            file = FIXTURES / (path.split('/')[-2].lower() + '-detail.xml')
        body = file.read_text()
        if url.endswith('?mode=cascade'):
            subject = path.rsplit('/', 1)[-1].split('.')[0]
            root = parse_xml(body, 'subject')
            root.remove(root.find('courses'))
            course = parse_xml((FIXTURES / (subject.lower() + '-detail.xml')).read_text(), 'course')
            course.tag = 'cascadingCourse'
            ET.SubElement(root, 'cascadingCourses').append(course)
            body = ET.tostring(root, encoding='unicode')
        match = re.search(r'/schedule/(\d{4})/(winter|spring|summer|fall)', url)
        if match:
            year, season = match.groups()
            term_code = {'winter': '0', 'spring': '1', 'summer': '5', 'fall': '8'}[season]
            body = (body.replace('/2026/fall', f'/{year}/{season}')
                    .replace('/2026.xml', f'/{year}.xml').replace('Fall 2026', f'{season.title()} {year}')
                    .replace('id="2026"', f'id="{year}"').replace('id="120268"', f'id="1{year}{term_code}"'))
        return {'url': url, 'fetched_at': FIXTURE_TIME, 'body': body}


class RecordingClient(FixtureClient):
    def __init__(self):
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        return super().fetch(url, **kwargs)


def fixture_snapshot(year=2026, season='fall'):
    discovery = CourseExplorerDiscovery(FixtureClient())
    term, _ = discovery.term(year, season)
    snapshot = merge_departments([department_snapshot(discovery, term, subject)
                                  for subject in subjects_for(discovery, term)])
    snapshot['data_kind'] = 'development_fixture'
    return snapshot


def archive_fixture(current=None):
    discovery = CourseExplorerDiscovery(FixtureClient())
    expected = requested_terms(2025, '2026-fall')
    snapshots, departments, rows = [], {}, []
    for term_id in expected:
        year, season = term_id.split('-')
        term, evidence = discovery.term(int(year), season)
        row = {'term_id': term_id, 'status': 'unavailable', **evidence,
               'department_count': 0, 'course_count': 0, **counts([])}
        if term:
            snapshot = deepcopy(current) if current and term_id == current['term']['id'] else fixture_snapshot(int(year), season)
            subjects = sorted({course['course_code'].split()[0] for course in snapshot['courses']})
            departments[term_id] = {'term_id': term_id, 'discovered_subjects': subjects, 'requested_subjects': subjects,
                'departments': [{'subject': subject, 'status': 'collected',
                    'course_count': sum(course['course_code'].startswith(subject + ' ') for course in snapshot['courses']),
                    **counts([section for section in snapshot['sections'] if section['course_code'].startswith(subject + ' ')])}
                    for subject in subjects]}
            snapshots.append(snapshot)
            row.update(status='collected', term=term, department_count=len(subjects),
                       course_count=len(snapshot['courses']), **counts(snapshot['sections']))
        rows.append(row)
    return validate_archive({'schema_version': 2, 'dataset': 'teaching_history', 'data_kind': 'development_fixture',
        'start_year': 2025, 'through_term': '2026-fall', 'requested_terms': expected,
        'collected_at': FIXTURE_TIME, 'discovery_sources': list(discovery.sources.values()),
        'snapshots': snapshots, 'department_coverage': departments,
        'coverage': {'terms': rows, 'totals': totals(rows)}})
