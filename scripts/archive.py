"""Campus-wide history, stored as a small index and immutable per-term files."""

from collections import defaultdict
from pathlib import Path

from scripts.course_explorer_discovery import CourseExplorerDiscovery
from scripts.data_contract import API_BASE, DataError, require, timestamp, validate_snapshot
from scripts.teaching_history import COUNT_FIELDS, counts, parse_term_id

SEASONS = ('winter', 'spring', 'summer', 'fall')


def requested_terms(start_year, through_term):
    end_year, end_season = parse_term_id(through_term)
    require(type(start_year) is int and 1900 <= start_year <= end_year, 'Invalid archive start year')
    return [f'{year}-{season}' for year in range(start_year, end_year + 1)
            for season in SEASONS if year < end_year or SEASONS.index(season) <= SEASONS.index(end_season)]


def validate_department_coverage(snapshot, coverage):
    require(coverage['term_id'] == snapshot['term']['id'], 'Department coverage term mismatch')
    subjects = coverage['discovered_subjects']
    require(subjects and len(set(subjects)) == len(subjects), 'Missing/duplicate discovered departments')
    require(coverage['requested_subjects'] == subjects, 'Production archive requires every discovered department')
    require([row['subject'] for row in coverage['departments']] == subjects, 'Incomplete department coverage')
    courses = defaultdict(list)
    sections = defaultdict(list)
    for course in snapshot['courses']:
        courses[course['course_code'].split()[0]].append(course)
    for section in snapshot['sections']:
        sections[section['course_code'].split()[0]].append(section)
    require(set(courses) <= set(subjects), 'Unexpected department in archive')
    for row in coverage['departments']:
        subject = row['subject']
        require(row['status'] == ('collected' if courses[subject] else 'no_listings'), 'Failed/inconsistent department coverage')
        require(row['course_count'] == len(courses[subject]), 'Department course count mismatch')
        require(all(row[key] == value for key, value in counts(sections[subject]).items()), 'Department meeting/instructor count mismatch')
    return coverage


def totals(rows):
    result = {key: sum(row[key] for row in rows) for key in (*COUNT_FIELDS, 'course_count', 'department_count')}
    result.update(requested_terms=len(rows), collected_terms=sum(row['status'] == 'collected' for row in rows),
                  unavailable_terms=sum(row['status'] == 'unavailable' for row in rows))
    return result


def validate_archive(history):
    """Validate a materialized archive; publication removes its large in-memory arrays."""
    try:
        require(history['schema_version'] == 2 and history['dataset'] == 'teaching_history', 'Unsupported archive format')
        require(history['data_kind'] in ('live', 'development_fixture'), 'Invalid archive kind')
        expected = requested_terms(history['start_year'], history['through_term'])
        require(history['requested_terms'] == expected, 'Archive range/request mismatch')
        sources = {row['url']: row['fetched_at'] for row in history['discovery_sources']}
        require(len(sources) == len(history['discovery_sources']) and API_BASE + '.xml' in sources, 'Missing/duplicate discovery evidence')
        for url, fetched_at in sources.items():
            require(url.startswith(API_BASE), 'Unexpected discovery source')
            timestamp(fetched_at)
        snapshots = {snapshot['term']['id']: snapshot for snapshot in history['snapshots']}
        require(len(snapshots) == len(history['snapshots']), 'Duplicate archive term')
        rows = history['coverage']['terms']
        require([row['term_id'] for row in rows] == expected, 'Incomplete archive term coverage')
        collected = set()
        for row in rows:
            term_id = row['term_id']
            year, _ = parse_term_id(term_id)
            require(row['source_url'] in sources and row['checked_at'] == sources[row['source_url']], 'Missing availability provenance')
            if row['status'] == 'unavailable':
                expected_url = API_BASE + '.xml' if row['reason'] == 'year_not_listed' else f'{API_BASE}/{year}.xml'
                require(row['reason'] in ('year_not_listed', 'term_not_listed') and row['source_url'] == expected_url, 'Invalid unavailable-term evidence')
                require(all(row[key] == 0 for key in (*COUNT_FIELDS, 'course_count', 'department_count')), 'Unavailable terms cannot have assignments')
            else:
                require(row['status'] == 'collected' and row['reason'] == 'term_listed', 'Failed collection cannot be published')
                require(row['source_url'] == f'{API_BASE}/{year}.xml', 'Invalid term discovery URL')
                snapshot = validate_snapshot(snapshots[term_id])
                require(snapshot['term'] == row['term'] and snapshot['data_kind'] == history['data_kind'], 'Archive term/kind mismatch')
                coverage = validate_department_coverage(snapshot, history['department_coverage'][term_id])
                require(row['course_count'] == len(snapshot['courses']) and row['department_count'] == len(coverage['departments']), 'Archive listing/department count mismatch')
                require(all(row[key] == value for key, value in counts(snapshot['sections']).items()), 'Archive counts mismatch')
                collected.add(term_id)
        require(set(snapshots) == collected == set(history['department_coverage']), 'Unexpected/missing archive snapshots')
        require([snapshot['term']['id'] for snapshot in history['snapshots']] == [row['term_id'] for row in rows if row['status'] == 'collected'], 'Archive snapshots are out of term order')
        require(history['coverage']['totals'] == totals(rows), 'Archive totals mismatch')
        times = list(sources.values()) + [snapshot['collected_at'] for snapshot in snapshots.values()]
        require(history['collected_at'] == max(times, key=timestamp), 'Archive timestamp mismatch')
    except (KeyError, TypeError, AttributeError) as error:
        raise DataError(f'Malformed campus archive: {error}') from error
    return history


def collect_archive(client, start_year, through_term, existing=None, current=None,
                    refresh=False, allow_collection=True, candidate_dir=Path('data/snapshots/archive')):
    expected = requested_terms(start_year, through_term)
    if not allow_collection:
        require(not refresh and existing is not None and existing.get('schema_version') == 2,
                'Full history is not archived; run update_data without --reuse-current')
        validate_archive(existing)
        require(existing['requested_terms'] == expected, 'Configured archive range is not saved; run a normal update')
        return existing
    from scripts.collect_campus import collect
    from scripts.integration import read
    discovery = CourseExplorerDiscovery(client)
    old = {snapshot['term']['id']: snapshot for snapshot in existing['snapshots']} if existing and existing.get('schema_version') == 2 else {}
    snapshots, coverage_by_term, rows = [], {}, []
    for term_id in expected:
        term, evidence = discovery.term(*parse_term_id(term_id))
        row = {'term_id': term_id, 'status': 'unavailable', **evidence,
               'course_count': 0, 'department_count': 0, **counts([])}
        if term:
            path = Path(candidate_dir)/(term_id + '.json')
            if current and term_id == current[0]['term']['id']:
                snapshot, coverage = current
            elif not refresh and term_id in old:
                snapshot, coverage = old[term_id], existing['department_coverage'][term_id]
                print(f'{term_id}: reused committed archive', flush=True)
            elif not refresh and path.exists() and path.with_suffix('.coverage.json').exists():
                snapshot, coverage = read(path), read(path.with_suffix('.coverage.json'))
                print(f'{term_id}: validating saved complete candidate', flush=True)
            else:
                snapshot = collect(client, term_id, path)
                coverage = read(path.with_suffix('.coverage.json'))
            validate_snapshot(snapshot)
            require(snapshot['term'] == term, 'Archived term differs from discovery')
            validate_department_coverage(snapshot, coverage)
            snapshots.append(snapshot)
            coverage_by_term[term_id] = coverage
            row.update(status='collected', term=term, course_count=len(snapshot['courses']),
                       department_count=len(coverage['departments']), **counts(snapshot['sections']))
        rows.append(row)
    sources = list(discovery.sources.values())
    history = {'schema_version': 2, 'dataset': 'teaching_history', 'data_kind': 'live',
               'start_year': start_year, 'through_term': through_term, 'requested_terms': expected,
               'discovery_sources': sources, 'snapshots': snapshots, 'department_coverage': coverage_by_term,
               'collected_at': max([source['fetched_at'] for source in sources] + [snapshot['collected_at'] for snapshot in snapshots], key=timestamp),
               'coverage': {'terms': rows, 'totals': totals(rows)}}
    return validate_archive(history)


def stage_archive(history, write_object):
    """Keep index metadata small; reuse identical content-addressed term objects."""
    validate_archive(history)
    index = {key: value for key, value in history.items() if key not in ('snapshots', 'department_coverage', 'coverage')}
    snapshots = {snapshot['term']['id']: snapshot for snapshot in history['snapshots']}
    rows = []
    for row in history['coverage']['terms']:
        references = {'snapshot': None, 'department_coverage': None}
        if row['status'] == 'collected':
            references = {'snapshot': write_object(snapshots[row['term_id']]),
                          'department_coverage': write_object(history['department_coverage'][row['term_id']], snapshots[row['term_id']]['collected_at'])}
        rows.append({**row, **references})
    index['coverage'] = {'terms': rows, 'totals': history['coverage']['totals']}
    return index


def load_archive(index, read_object):
    history = {key: value for key, value in index.items() if key != 'coverage'}
    rows, snapshots, departments = [], [], {}
    for row in index['coverage']['terms']:
        if row['status'] == 'collected':
            snapshot = read_object(row['snapshot'])
            require(row['snapshot']['collected_at'] == row['department_coverage']['collected_at'] == snapshot['collected_at'], 'Archive object timestamp mismatch')
            snapshots.append(snapshot)
            departments[row['term_id']] = read_object(row['department_coverage'])
        else:
            require(row['snapshot'] is None and row['department_coverage'] is None, 'Unavailable term has data references')
        rows.append({key: value for key, value in row.items() if key not in ('snapshot', 'department_coverage')})
    history.update(snapshots=snapshots, department_coverage=departments,
                   coverage={'terms': rows, 'totals': index['coverage']['totals']})
    return validate_archive(history)


def render_archive_report(history):
    validate_archive(history)
    total = history['coverage']['totals']
    lines = ['# Teaching-history coverage', '',
             f'Campus-wide archive: **{history["start_year"]} through {history["through_term"]}**. Data kind: `{history["data_kind"]}`.',
             f'Latest successful source/discovery fetch: `{history["collected_at"]}`.', '',
             f'{total["requested_terms"]} requested terms; {total["collected_terms"]} collected; {total["unavailable_terms"]} confirmed unavailable.',
             f'{total["course_count"]:,} course/term listings; {total["section_count"]:,} registration sections; {total["meeting_count"]:,} meetings.', '',
             '| Term | Status | Departments | Listings | Sections | Meetings | Missing instructors | Multiple instructors | Unresolved occurrences |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in history['coverage']['terms']:
        lines.append('| ' + ' | '.join(str(row[key]) for key in ('term_id', 'status', 'department_count', 'course_count', *COUNT_FIELDS[:4], 'unresolved_occurrences')) + ' |')
    lines += ['', 'Every collected term covers all departments listed by its official index. Sections and cross-listed registrations remain separate. Missing/multiple counts refer to meetings; unresolved occurrences are not unique people.', '',
              '## Availability and provenance', '']
    for row in history['coverage']['terms']:
        lines.append(f'- `{row["term_id"]}`: {row["status"]} ({row["reason"]}); [official index]({row["source_url"]}), fetched `{row["checked_at"]}`.')
    lines += ['', 'The public history index links each term’s complete schedule and department coverage with SHA-256, byte size, and original source timestamp. Original instructor names and meeting roles remain on the term snapshots. Identities are unresolved until separately verified.', '']
    return '\n'.join(lines)
