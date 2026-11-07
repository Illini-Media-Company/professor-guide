"""Include official faculty-directory identities independently of GPA data.

Directory membership establishes name/NetID evidence, not course assignments.
Existing identity IDs, grades, occurrence links and ratings are preserved.
"""

import argparse
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from scripts.data_contract import atomic_write_json, timestamp
from scripts.integration import read, validate_input
from scripts.review_identities import (DirectoryParser, FACULTY_URL, GraingerDirectory,
                                       SourceCache, full_name_agrees, now)


def merge_faculty(professors, rows, sources, reviewed_at):
    result = deepcopy(professors)
    existing = {p['institutional_id']: p for p in result['records'] if p.get('institutional_id')}
    uri_profiles = [p for p in result['records'] if p.get('directory_profile_url') and not p.get('institutional_id')]
    grouped, held, added = defaultdict(list), [], []
    for row in rows:
        grouped[row['netid']].append(row)
    for netid, evidence in sorted(grouped.items()):
        if netid in existing:
            continue
        possible = [p['professor_id'] for p in uri_profiles if any(
            full_name_agrees(row['name'], p['display_name']) if ',' in row['name'] else
            full_name_agrees(p['display_name'].rsplit(' ', 1)[-1] + ', ' + p['display_name'].rsplit(' ', 1)[0], row['name'])
            for row in evidence)]
        if possible:
            held.append({'directory_id': netid, 'possible_existing_profile_ids': possible,
                         'reason': 'Name already visible; NetID/profile reconciliation remains pending.'})
            continue
        # Prefer the named department's own roster over the campus rollup.
        chosen = max(evidence, key=lambda row: (row['source_url'] != FACULTY_URL, len(row['name'])))
        name = chosen['name']
        if ',' in name:
            last, given = name.split(',', 1)
            name = given.strip() + ' ' + last.strip()
        urls = sorted({row['source_url'] for row in evidence})
        profiles = sorted({row['profile_url'] for row in evidence if row.get('profile_url')})
        person = {'professor_id': 'prof_uiuc_' + netid, 'institutional_id': netid, 'display_name': name,
            'identity_source': 'official_faculty_directory',
            'official_names': sorted({row['name'] for row in evidence}),
            'department_names': sorted({row['unit'] for row in evidence}),
            'identity_evidence': [f'Official university faculty directories bind {name} to public university identifier {netid}.',
                                  'Directory identity is independent of GPA availability. No course assignment or GPA is inferred from matching initials.',
                                  'Directory sources: ' + ', '.join(urls)],
            'identity_sources': [{key: sources[url][key] for key in ('url', 'fetched_at', 'sha256')} for url in urls],
            'faculty_links': [{'url': url, 'evidence': 'Official faculty roster publishes this name, university identifier and profile link.',
                              'verified_at': reviewed_at} for url in (profiles[:1] or urls[:1])],
            'rmp': None}
        result['records'].append(person)
        existing[netid] = person
        added.append(person['professor_id'])
    merged = {s['url']: s['fetched_at'] for s in result['sources']}
    merged.update({url: source['fetched_at'] for url, source in sources.items()})
    result['sources'] = [{'url': url, 'fetched_at': value} for url, value in sorted(merged.items())]
    result['collected_at'] = max(merged.values(), key=timestamp)
    validate_input(result, 'professors')
    return result, {'reviewed_at': reviewed_at, 'source_directory_id_count': len(grouped),
                    'added_professor_ids': added, 'held_for_reconciliation': held,
                    'sources': [{key: source[key] for key in ('url', 'fetched_at', 'sha256')} for source in sources.values()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-sources', action='store_true')
    args = parser.parse_args()
    cache = SourceCache('.cache/identity-review', offline=args.reuse_sources)
    config = read('config/identity-review.json')
    response = cache.fetch(FACULTY_URL)
    campus = DirectoryParser(FACULTY_URL)
    campus.feed(response['body'])
    rows, sources = campus.people, {FACULTY_URL: response}
    for spec in config.get('grainger_rosters', []):
        response = cache.fetch(spec['url'])
        directory = GraingerDirectory(spec)
        directory.feed(response['body'])
        rows.extend(directory.people)
        sources[spec['url']] = response
    result, review = merge_faculty(read('data/inputs/professors.json'), rows, sources, now())
    atomic_write_json('data/inputs/professors.json', result)
    atomic_write_json('data/mappings/faculty-directory-review.json', review)
    print(f"Added {len(review['added_professor_ids'])} faculty identities; {len(review['held_for_reconciliation'])} possible duplicate identities held; {len(result['records'])} identified instructors total.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
