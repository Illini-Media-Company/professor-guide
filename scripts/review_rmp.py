"""Audit a fixed instructor set against RMP's public school directory.

Use the anonymous GraphQL pagination used by the public search interface.
Collect professional identity, aggregate metrics and course codes only; no
individual reviews or account data. This command never publishes the site.
"""

import argparse
import csv
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import time

from scripts.data_contract import DataError, atomic_write_json, atomic_write_text, require, timestamp
from scripts.integration import read, validate_input
from scripts.review_identities import full_name_agrees, name_parts, unit_tokens, words


API = 'https://www.ratemyprofessors.com/graphql'
SCHOOL_ID = 'U2Nob29sLTExMTI='
SCHOOL_NAME = 'University Of Illinois at Urbana - Champaign'
OUTCOMES = {'verified_match', 'ambiguous_candidates', 'no_matching_profile_found', 'lookup_unavailable'}
METRICS = ('overall_quality', 'num_ratings', 'difficulty', 'would_take_again_percent')
QUERY = '''query ProfessorGuideDirectory($count: Int!, $cursor: String, $query: TeacherSearchQuery!) {
  search: newSearch {
    teachers(query: $query, first: $count, after: $cursor) {
      resultCount didFallback
      edges { cursor node {
        id legacyId firstName lastName department
        school { id name }
        avgRating numRatings avgDifficulty wouldTakeAgainPercent
        courseCodes { courseName }
      } }
      pageInfo { hasNextPage endCursor }
    }
  }
}'''


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def identity_fingerprint(professors):
    identities = [{key: value for key, value in person.items() if key not in ('rmp',)}
                  for person in professors['records']]
    return sha(json.dumps(identities, sort_keys=True, ensure_ascii=False).encode())


class DirectoryClient:
    def __init__(self, cache_dir, offline=False, pace=1.0):
        self.directory, self.offline, self.pace = Path(cache_dir), offline, pace
        self.last_request = 0
        self.blocked_path = self.directory / 'access-denial.json'

    def page(self, cursor):
        request = {'query': QUERY, 'operationName': 'ProfessorGuideDirectory',
                   'variables': {'count': 100, 'cursor': cursor,
                                 'query': {'schoolID': SCHOOL_ID, 'text': '', 'fallback': False}}}
        body = json.dumps(request, sort_keys=True).encode()
        key = sha(body)
        path = self.directory / (key + '.json')
        if path.exists():
            saved = read(path)
            require(saved['request_sha256'] == key and saved['response_sha256'] ==
                    sha(json.dumps(saved['data'], sort_keys=True).encode()), 'RMP cache integrity failure')
            timestamp(saved['fetched_at'])
            return saved
        require(not self.offline, 'No cached RMP directory page; directory coverage is incomplete')
        if self.blocked_path.exists():
            denied = read(self.blocked_path)
            require((datetime.now(timezone.utc) - timestamp(denied['checked_at'])).total_seconds() >= 86400,
                    'RMP access deferred after denial; no further requests made')
        delay = self.pace - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()
        response = subprocess.run(['curl', '--silent', '--show-error', '--max-time', '30',
            '--proto', '=https', '-H', 'Content-Type: application/json',
            '--data-binary', '@-', '--write-out', '\n%{http_code}', API],
            input=body, capture_output=True, timeout=35)
        require(response.returncode == 0, 'RMP directory network request failed')
        raw, status = response.stdout.rsplit(b'\n', 1)
        code = int(status)
        if code in (202, 401, 403, 429):
            atomic_write_json(self.blocked_path, {'checked_at': now(), 'http_status': code, 'url': API})
        require(code == 200, f'RMP directory unavailable: HTTP {code}')
        parsed = json.loads(raw)
        require(not parsed.get('errors'), f"RMP directory query failed: {parsed.get('errors')}")
        data = parsed['data']['search']['teachers']
        saved = {'url': API, 'request_sha256': key, 'request': request,
                 'raw_response_sha256': sha(raw), 'response_sha256': sha(json.dumps(data, sort_keys=True).encode()),
                 'fetched_at': now(), 'data': data}
        atomic_write_json(path, saved)
        return saved


def collect_directory(client):
    nodes, pages, failures, seen_cursors = {}, [], [], set()
    returned_entries, duplicate_ids = 0, set()
    cursor, expected, complete = '', None, False
    try:
        while True:
            require(cursor not in seen_cursors, 'RMP directory repeated a pagination cursor')
            seen_cursors.add(cursor)
            page = client.page(cursor)
            data = page['data']
            require(data.get('didFallback') is False, 'RMP directory used fallback results')
            require(type(data['resultCount']) is int and data['resultCount'] >= 0, 'Invalid RMP directory size')
            expected = data['resultCount'] if expected is None else expected
            require(expected == data['resultCount'], 'RMP directory size changed during pagination; rerun review')
            require(len(pages) < 200, 'Unexpected RMP directory pagination size')
            source = {key: value for key, value in page.items() if key != 'data'}
            pages.append(source)
            for edge in data['edges']:
                returned_entries += 1
                node = edge['node']
                require(node['school']['id'] == SCHOOL_ID and node['school']['name'] == SCHOOL_NAME,
                        'RMP directory returned a different university')
                identifier = node['legacyId']
                require(type(identifier) is int and identifier > 0, 'Invalid RMP profile ID during pagination')
                if identifier in nodes:
                    require(all(nodes[identifier][key] == node[key] for key in ('firstName', 'lastName', 'school', 'department')),
                            'Repeated RMP profile has conflicting identity fields')
                    duplicate_ids.add(identifier)
                nodes[identifier] = {**node, '_source': {key: source[key] for key in
                    ('url', 'request_sha256', 'response_sha256', 'fetched_at')}}
            print(f'RMP directory: {returned_entries}/{expected} result entries; {len(nodes)} unique profiles', flush=True)
            if not data['pageInfo']['hasNextPage']:
                require(returned_entries == expected, 'Incomplete RMP directory results')
                complete = True
                break
            require(data['edges'] and data['pageInfo']['endCursor'], 'Empty RMP pagination page')
            cursor = data['pageInfo']['endCursor']
    except (DataError, KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        failures.append({'url': API, 'reason': str(error), 'checked_at': now()})
    return list(nodes.values()), {'complete': complete, 'expected_profiles': expected,
                                  'returned_entries': returned_entries, 'duplicate_profile_ids': sorted(duplicate_ids),
                                  'collected_profiles': len(nodes), 'pages': pages, 'failures': failures}


def course_key(code):
    return re.sub(r'[^A-Z0-9]', '', code.upper())


def context_for(professors, identity_ledger, links, grades):
    """Use established identity evidence and verified GPA links only."""
    contexts = {person['professor_id']: {'names': {person['display_name'], *person.get('official_names', [])}, 'units': set(person.get('department_names', [])),
                'courses': set(), 'official_sources': {link['url'] for link in person.get('faculty_links', [])}}
                for person in professors['records']}
    by_key = {}
    for person in professors['records']:
        identifier = person.get('institutional_id')
        if person.get('directory_profile_url'):
            identifier = 'profile_' + sha(person['directory_profile_url'].encode())[:24]
        if identifier:
            by_key[identifier] = contexts[person['professor_id']]
    for entry in identity_ledger['identities']:
        if entry['status'] != 'verified_identity' or entry['netid'] not in by_key:
            continue
        context = by_key[entry['netid']]
        for candidate in entry['candidates']:
            if candidate['netid'] == entry['netid']:
                context['names'].update(candidate['official_names'])
                context['units'].update(candidate['units'])
                context['official_sources'].update(candidate['source_urls'])
    by_grade = {grade['id']: grade for grade in grades['records']}
    for link in links['records']:
        context = contexts.get(link['professor_id'])
        if context is not None and link['verified'] is True:
            context['courses'].add(course_key(link['listing_id'].split(':', 1)[1]))
            for match in link.get('grade_name_matches', []):
                grade = by_grade[match['grade_record_id']]
                context['courses'].add(course_key(grade['course_code']))
    return contexts


def department_matches(department, units, aliases):
    alternatives = aliases.get(department, [])
    if isinstance(alternatives, str):
        alternatives = [alternatives]
    for label in [department, *alternatives]:
        tokens = unit_tokens(label)
        if tokens and any(tokens == unit_tokens(unit) or
                (len(tokens) >= 2 and unit_tokens(unit)[:len(tokens)] == tokens) for unit in units):
            return True
    return False


def metrics(node):
    count = node['numRatings']
    require(type(count) is int and count >= 0, 'Invalid RMP rating count')
    values = {'num_ratings': count}
    for source, target, minimum, maximum in (
        ('avgRating', 'overall_quality', 0, 5), ('avgDifficulty', 'difficulty', 0, 5),
        ('wouldTakeAgainPercent', 'would_take_again_percent', 0, 100)):
        value = node.get(source)
        if value is None or value == -1 or count == 0 or (target != 'would_take_again_percent' and value == 0):
            value = None
        require(value is None or (type(value) in (int, float) and minimum <= value <= maximum),
                f'Invalid RMP {target}')
        values[target] = value
    return values


def audit(professors, contexts, nodes, directory, config, reviewed_at):
    by_last = defaultdict(list)
    for node in nodes:
        by_last[tuple(words(node['lastName']))].append(node)
    entries = []
    for person in professors['records']:
        context = contexts[person['professor_id']]
        # Split natural names in every possible way; RMP supplies the surname
        # boundary. Full first/surname confirmation still happens below.
        surnames = set()
        for name in context['names']:
            if ',' in name:
                last = name_parts(name)[0]
                surnames.update(tuple(last[:cut]) for cut in range(1, len(last) + 1))
            else:
                tokens = words(name)
                surnames.update(tuple(tokens[start:end]) for start in range(1, len(tokens))
                                for end in range(start + 1, len(tokens) + 1))
        possible = {node['legacyId']: node for last in surnames for node in by_last.get(last, [])}
        candidates, supported = [], []
        for node in possible.values():
            rmp_name = f"{node['lastName']}, {node['firstName']}"
            full = any(full_name_agrees(rmp_name, name) for name in context['names'])
            # Initial/nickname candidates remain explicitly unverified.
            given = words(node['firstName'])
            plausible = full or any((parts := (name_parts(name)[1] if ',' in name else words(name)))
                                   and given and parts[0][0] == given[0][0] for name in context['names'])
            if not plausible:
                continue
            same_department = department_matches(node['department'], context['units'], config.get('department_aliases', {}))
            shared = sorted(context['courses'] & {course_key(x['courseName']) for x in node.get('courseCodes', [])})
            candidate = {'profile_id': node['legacyId'], 'profile_url': f"https://www.ratemyprofessors.com/professor/{node['legacyId']}",
                'name': rmp_name, 'school': node['school']['name'], 'school_id': node['school']['id'], 'department': node['department'],
                'full_name_agrees': full, 'department_agrees': same_department, 'shared_courses': shared,
                'raw_metrics': {key: node.get(key) for key in ('avgRating', 'numRatings', 'avgDifficulty', 'wouldTakeAgainPercent')},
                'metrics': metrics(node), 'source': node['_source']}
            candidates.append(candidate)
            if full and (same_department or shared):
                supported.append(candidate)
        entry = {'professor_id': person['professor_id'], 'display_name': person['display_name'],
                 'checked_at': reviewed_at, 'status': 'lookup_unavailable',
                 'reason': 'incomplete_directory', 'candidates': sorted(candidates, key=lambda c: c['profile_id']),
                 'official_sources': sorted(context['official_sources']), 'official_names': sorted(context['names']),
                 'official_units': sorted(context['units']), 'verified_courses': sorted(context['courses']), 'rmp': None}
        if len(supported) == 1 and directory['complete']:
            candidate = supported[0]
            entry.update(status='verified_match', reason='unique_full_name_school_and_context',
                rmp={'scope': 'professor', **candidate['metrics'], 'source_url': candidate['profile_url'],
                     'collected_at': candidate['source']['fetched_at'], 'profile_id': candidate['profile_id'],
                     'retrieved_from': candidate['source'], 'verified_at': reviewed_at,
                     'reviewed_by': 'Codex (RMP public directory context v1)',
                     'matching_evidence': [f"Full name agrees with established official identity; RMP school is {SCHOOL_NAME}.",
                         f"RMP department {candidate['department']} agrees with official unit evidence." if candidate['department_agrees']
                         else 'RMP course codes agree with verified GPA course context: ' + ', '.join(candidate['shared_courses'])]})
        elif directory['complete']:
            entry.update(status='ambiguous_candidates' if candidates else 'no_matching_profile_found',
                         reason='multiple_supported_profiles' if len(supported) > 1 else
                                'name_or_context_requires_review' if candidates else 'no_name_candidate_in_complete_school_directory')
        entries.append(entry)
    # A single RMP identity cannot silently be assigned to two guide identities.
    owners = defaultdict(list)
    for entry in entries:
        if entry['rmp'] is not None:
            owners[entry['rmp']['profile_id']].append(entry)
    for shared in owners.values():
        if len(shared) > 1:
            for entry in shared:
                entry.update(status='ambiguous_candidates', reason='profile_shared_by_multiple_guide_identities', rmp=None)
    return entries


def validate_audit(ledger, professors):
    expected = {p['professor_id'] for p in professors['records']}
    entries = ledger['records']
    require(len(entries) == len(expected) and {e['professor_id'] for e in entries} == expected,
            'RMP audit must account for the fixed instructor set exactly once')
    claimed = set()
    for entry in entries:
        require(entry['status'] in OUTCOMES, 'Unknown RMP audit outcome')
        timestamp(entry['checked_at'])
        rmp = entry['rmp']
        require((rmp is not None) == (entry['status'] == 'verified_match'), 'RMP outcome and rating disagree')
        if rmp is None:
            continue
        require(rmp['profile_id'] not in claimed, 'RMP profile assigned twice')
        claimed.add(rmp['profile_id'])
        require(ledger['directory']['complete'], 'Incomplete lookup cannot establish a unique RMP match')
        candidate = next(c for c in entry['candidates'] if c['profile_id'] == rmp['profile_id'])
        require(candidate['school_id'] == SCHOOL_ID and candidate['school'] == SCHOOL_NAME and candidate['full_name_agrees'] and
                (candidate['department_agrees'] or candidate['shared_courses']), 'Missing RMP identity evidence')
        require(entry['official_sources'] and rmp['matching_evidence'], 'RMP match needs official identity provenance')
        require(rmp['retrieved_from']['url'] == API and rmp['retrieved_from']['request_sha256'] and
                rmp['retrieved_from']['response_sha256'], 'RMP metrics need retrieval provenance')
        require(rmp['retrieved_from'] == candidate['source'] and rmp['collected_at'] == candidate['source']['fetched_at'],
                'RMP rating disagrees with its retrieval provenance')
        require(rmp['source_url'] == candidate['profile_url'], 'RMP profile URL disagrees with match')
        require(candidate['metrics'] == metrics(candidate['raw_metrics']), 'RMP metric normalization differs from source')
        for metric in METRICS:
            require(rmp[metric] == candidate['metrics'][metric], 'RMP metric differs from its source')
        timestamp(rmp['collected_at'])
        require(timestamp(rmp['verified_at']) >= timestamp(rmp['collected_at']), 'RMP review predates retrieval')
    return ledger


def write_reports(ledger):
    entries = ledger['records']
    counts = Counter(entry['status'] for entry in entries)
    matched = [entry for entry in entries if entry['rmp'] is not None]
    available = {key: sum(e['rmp'][key] is not None for e in matched) for key in METRICS}
    ledger['summary'] = {'instructors': len(entries), 'outcomes': {key: counts[key] for key in sorted(OUTCOMES)},
                         'metric_availability': available,
                         'matched_percent': round(100 * len(matched) / len(entries), 2)}
    lines = ['# RMP coverage audit', '', f"Checked at `{ledger['checked_at']}`.", '',
        f"**{len(matched):,} of {len(entries):,} instructors ({ledger['summary']['matched_percent']}%)** have a unique supported RMP match.",
        '', f"School-directory coverage: {ledger['directory']['returned_entries']:,} of {ledger['directory']['expected_profiles']} result entries, representing {ledger['directory']['collected_profiles']:,} distinct profiles; pagination complete: {str(ledger['directory']['complete']).lower()}.",
        f"Repeated profile IDs returned by the directory: {len(ledger['directory']['duplicate_profile_ids'])}. Repeated IDs are counted once; conflicting identity fields stop the audit.",
        '', '| Outcome | Instructors |', '| --- | ---: |']
    lines += [f'| {status} | {counts[status]:,} |' for status in sorted(OUTCOMES)]
    lines += ['', '## Metric availability', '', '| Metric | Matched instructors with a value |', '| --- | ---: |']
    lines += [f'| {key} | {value:,} |' for key, value in available.items()]
    lines += ['', '## Method and limits', '',
        'The audit compares the fixed accepted instructor set with the public RMP school-directory results for University Of Illinois at Urbana - Champaign. A match requires a compatible full first/surname, compatible supplied middle names, the correct school, and official department or verified course context. Initial-only and nickname candidates require further review; multiple supported profiles and shared profile assignments remain ambiguous.',
        '', 'These are bulk rule-based matches, not individual manual investigations. RMP course codes are supporting profile context; they do not make its aggregate ratings course-specific. The source is an anonymous query to the same public directory endpoint and pagination interface used by the RMP website, requesting its public profile summary/course fields. No individual review text is collected. Profile URLs identify the rated person; retrieval timestamps and query/response hashes identify where each metric was actually fetched.',
        '', 'Missing values and source sentinel values remain null; a genuine zero-percent take-again value is retained. Rating counts are counts of reviews, not graded enrollments. Failure or incomplete pagination is lookup unavailable, never evidence of absence. A no-match outcome means no name candidate was found in the directory results returned during this run; it does not establish that no profile exists. Repeated result IDs can reflect indexing or changing search order, so pagination completeness does not guarantee an exhaustive list of every real RMP profile.',
        '', '## Launch checkpoint', '',
        ('Launch decision: proceed with available verified ratings. Missing metrics and unmatched profiles display Pending; there is no minimum coverage requirement. Deployment remains paused. Wider GPA/archive identity expansion remains deferred.'
         if ledger.get('status') == 'available_ratings_with_pending_missing' else
         'No minimum ratings coverage is assumed. Stop here to decide launch coverage with the user. Deployment remains paused. Wider GPA/archive identity expansion remains deferred.'),
        '', 'See the [complete audit queue](../data/mappings/rmp-review.csv) and [evidence ledger](../data/mappings/rmp-identities.json).', '']
    for failure in ledger['directory']['failures']:
        lines += ['Source failure: ' + failure['reason'], '']
    atomic_write_text('docs/rmp-coverage.md', '\n'.join(lines))
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['professor_id', 'display_name', 'status', 'reason', 'profile_url', *METRICS, 'collected_at', 'candidate_profile_urls'])
    for entry in entries:
        rmp = entry['rmp'] or {}
        writer.writerow([entry['professor_id'], entry['display_name'], entry['status'], entry['reason'],
            rmp.get('source_url', ''), *(rmp.get(key, '') for key in METRICS), rmp.get('collected_at', ''),
            '; '.join(c['profile_url'] for c in entry['candidates'])])
    atomic_write_text('data/mappings/rmp-review.csv', output.getvalue())
    atomic_write_json('data/mappings/rmp-identities.json', ledger)


def export_ratings(professors, ledger):
    result = deepcopy(professors)
    sources = {source['url']: source['fetched_at'] for source in result['sources']}
    by_id = {entry['professor_id']: entry for entry in ledger['records']}
    for person in result['records']:
        entry = by_id[person['professor_id']]
        # Rebuild this audit's prior decisions; preserve independently authored summaries.
        if person.get('rmp') and person['rmp'].get('reviewed_by') != 'Codex (RMP public directory context v1)':
            require(person['rmp'] == entry['rmp'], 'Existing independent RMP review needs explicit reconciliation')
        person['rmp'] = entry['rmp']
        if entry['rmp'] is not None:
            fetched = entry['rmp']['collected_at']
            sources[API] = max([sources[API], fetched], key=timestamp) if API in sources else fetched
    result['sources'] = [{'url': url, 'fetched_at': fetched} for url, fetched in sorted(sources.items())]
    result['collected_at'] = max(sources.values(), key=timestamp)
    require(identity_fingerprint(result) == identity_fingerprint(professors), 'RMP audit changed the fixed instructor identities')
    return validate_input(result, 'professors')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=Path('.cache/rmp-review'))
    parser.add_argument('--reuse-sources', action='store_true')
    parser.add_argument('--apply', action='store_true', help='Update accepted RMP summaries; never publishes')
    args = parser.parse_args()
    professors = validate_input(read('data/inputs/professors.json'), 'professors')
    require(bool(professors['records']), 'RMP audit needs an identified instructor set')
    config = read('config/rmp-review.json')
    contexts = context_for(professors, read('data/mappings/professor-identities.json'),
                           read('data/inputs/verified-links.json'), read('data/inputs/gpa.json'))
    nodes, directory = collect_directory(DirectoryClient(args.cache_dir, args.reuse_sources))
    checked_at = now()
    entries = audit(professors, contexts, nodes, directory, config, checked_at)
    ledger = {'schema_version': 1, 'dataset': 'rmp_identity_review', 'checked_at': checked_at,
        'status': config.get('launch_policy', 'awaiting_launch_coverage_decision'), 'method': 'rmp_directory_context_v1',
        'inputs': {'identity_sha256': identity_fingerprint(professors),
                   'config_sha256': sha(Path('config/rmp-review.json').read_bytes()),
                   'script_sha256': sha(Path(__file__).read_bytes())},
        'directory': directory, 'records': entries}
    validate_audit(ledger, professors)
    if args.apply:
        require(directory['complete'], 'Incomplete directory audit cannot replace existing ratings')
        atomic_write_json('data/inputs/professors.json', export_ratings(professors, ledger))
    write_reports(ledger)
    print(json.dumps(ledger['summary'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
