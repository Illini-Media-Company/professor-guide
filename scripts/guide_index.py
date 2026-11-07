"""Small visitor-facing projection of verified identities and grade joins."""

from collections import defaultdict
import hashlib

def build_verified_guide_index(schedule, history, inputs, attributions):
    if not all(key in inputs for key in ('professors', 'gpa', 'verified_occurrences')):
        return None
    people = inputs['professors']['records']
    person_ids = {person['professor_id'] for person in people}
    links = defaultdict(lambda: defaultdict(set))
    for link in inputs['verified_occurrences']['records']:
        if link['verified'] and link['professor_id'] in person_ids:
            term, course = link['listing_id'].split(':', 1)
            links[link['professor_id']][course].add(term)
    accepted = {row['grade_record_id']: row['professor_id'] for row in attributions['grade_attributions']
                if row['status'] == 'verified'}
    grades = []
    for grade in inputs['gpa']['records']:
        person_id = accepted.get(grade['id'])
        if person_id is None:
            continue
        grades.append({key: grade[key] for key in ('id', 'course_code', 'term_id', 'grain', 'gpa', 'student_count')}
                      | {'professor_id': person_id})
        links[person_id][grade['course_code']].add(grade['term_id'])
    courses = {}
    terms = {}
    connected = {code for assignments in links.values() for code in assignments}
    snapshots = [*history['snapshots'], schedule]
    season_order = {'winter': 0, 'spring': 1, 'summer': 2, 'fall': 3}
    for snapshot in sorted(snapshots, key=lambda item: (item['term']['year'], season_order[item['term']['season']])):
        terms[snapshot['term']['id']] = snapshot['term']
        for course in snapshot['courses']:
            if course['course_code'] in connected:
                courses[course['course_code']] = {key: course.get(key) for key in
                    ('course_code', 'title', 'source_url', 'collected_at')}
    professors = []
    for person in people:
        rmp = person.get('rmp')
        professors.append({'professor_id': person['professor_id'], 'display_name': person['display_name'],
            'faculty_links': [{'url': link['url']} for link in person.get('faculty_links', [])],
            'rmp': {key: rmp.get(key) for key in ('overall_quality', 'num_ratings', 'difficulty',
                'would_take_again_percent', 'source_url', 'collected_at')} if rmp is not None else None,
            'courses': [{'course_code': code, 'term_ids': sorted(term_ids)}
                        for code, term_ids in sorted(links[person['professor_id']].items())]})
    used_terms = {term for assignments in links.values() for term_ids in assignments.values() for term in term_ids}
    return {'schema_version': 1, 'dataset': 'guide_index', 'data_kind': schedule['data_kind'],
        'collected_at': attributions['collected_at'], 'professors': professors,
        'courses': [courses.get(code, {'course_code': code, 'title': None, 'source_url': None, 'collected_at': None})
                    for code in sorted(connected)],
        'terms': [terms[term] for term in sorted(used_terms)], 'grade_records': grades,
        'gpa_sources': inputs['gpa']['sources'],
        'coverage': {'professors': len(professors), 'courses': len(connected), 'grade_records': len(grades)}}


def build_guide_index(schedule, history, inputs, attributions, schema_version=2):
    """Catalog visibility is independent of identity and grade availability.

    Unresolved names are subject-scoped source-label entries, never invented
    professor identities. Only individually reviewed occurrences are resolved.
    """
    if schema_version == 1:
        return build_verified_guide_index(schedule, history, inputs, attributions)
    available = {**inputs}
    for key in ('professors', 'gpa', 'verified_occurrences'):
        available.setdefault(key, {'records': [], 'sources': []})
    base = build_verified_guide_index(schedule, history, available, attributions)
    snapshots = {snapshot['term']['id']: snapshot for snapshot in [*history['snapshots'], schedule]}
    seasons = {'winter': 0, 'spring': 1, 'summer': 2, 'fall': 3}
    courses, course_terms, terms = {}, defaultdict(set), {}
    source_names = defaultdict(lambda: defaultdict(set))
    known = {(row['section_id'], row['meeting_id'], row['instructor_index'], row['name_raw'])
             for row in available['verified_occurrences']['records'] if row['verified']}
    assignment_count = 0
    for snapshot in sorted(snapshots.values(), key=lambda item: (item['term']['year'], seasons[item['term']['season']])):
        term = snapshot['term']['id']
        terms[term] = snapshot['term']
        for course in snapshot['courses']:
            code = course['course_code']
            course_terms[code].add(term)
            courses[code] = {key: course.get(key) for key in ('course_code', 'title', 'source_url', 'collected_at')}
        for section in snapshot['sections']:
            code = section['course_code']
            subject = code.split()[0]
            for meeting in section['meetings']:
                for position, instructor in enumerate(meeting['instructors']):
                    assignment_count += 1
                    raw = instructor['name_raw']
                    if (section['id'], meeting['id'], position, raw) not in known:
                        source_names[(subject, raw)][code].add(term)
    entries = []
    for (subject, raw), assignments in sorted(source_names.items()):
        entry_id = 'schedule_name_' + hashlib.sha256((subject + '\n' + raw).encode()).hexdigest()[:24]
        entries.append({'entry_id': entry_id, 'display_name': raw, 'subject': subject,
                        'courses': [{'course_code': code, 'term_ids': sorted(term_ids)}
                                    for code, term_ids in sorted(assignments.items())]})
    base.update(schema_version=2, catalog_scope='all_collected_courses', schedule_names=entries,
        courses=[{**courses[code], 'term_ids': sorted(course_terms[code])} for code in sorted(courses)],
        terms=[terms[term] for term in sorted(terms)],
        coverage={**base['coverage'], 'courses': len(courses), 'schedule_name_entries': len(entries),
                  'source_instructor_occurrences': assignment_count})
    return base
