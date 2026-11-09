"""Audit every GPA identity against official directories and saved schedules.

Only unique full-name matches with department and course/term evidence can
be exported. Name variants need explicit, separately sourced review.
Raw responses are cached outside publication; the ledger records evidence,
remaining work, and input fingerprints so review is repeatable.
"""

import argparse
import base64
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import io
from pathlib import Path
import re
import subprocess
import time
import unicodedata
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from scripts.data_contract import DataError, atomic_write_json, atomic_write_text, require, timestamp, validate_snapshot
from scripts.integration import read, read_object, validate_input


FACULTY_URL = 'https://directory.illinois.edu/facultyListing'
UNITS_URL = 'https://directory.illinois.edu/departmentsUnits'
REVIEW_METHOD = 'directory_context_v1'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def digest(body):
    return hashlib.sha256(body).hexdigest()


def minimize_directory_payload(value):
    """Keep public professional identity fields needed by this review only."""
    keep = {'count', 'people', 'items', 'office', 'offices', 'name', 'netId', 'netid', 'username',
            'firstName', 'firstNameReversed', 'firstname', 'lastName', 'lastname',
            'fullName', 'fullNameReversed', 'fullname', 'fullnamefirst', 'department', 'unit',
            'jobProfiles', 'jobType', 'title', 'primaryOffice', 'primaryTitle', 'officeType',
            'officeName', 'profileUrl', 'externalurlwithpath', 'source', 'isPublished', 'published'}
    if isinstance(value, list):
        return [minimize_directory_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: minimize_directory_payload(item) for key, item in value.items() if key in keep}
    return value


def words(value):
    decomposed = unicodedata.normalize('NFKD', value.casefold())
    return re.findall(r'[a-z0-9]+', ''.join(c for c in decomposed if not unicodedata.combining(c)))


def name_parts(value, surname=None):
    if ',' in value:
        last, given = value.split(',', 1)
        return words(last), words(given)
    tokens = words(value)
    while tokens and tokens[0] in ('dr', 'prof', 'professor'):
        tokens.pop(0)
    while tokens and tokens[-1] in ('phd', 'ph', 'md'):
        tokens.pop()
    if surname and tokens[-len(surname):] == surname:
        return surname, tokens[:-len(surname)]
    return [], []


def full_name_agrees(grade_name, official_name):
    """Require full first/surname tokens; supplied middle tokens must agree."""
    last, given = name_parts(grade_name)
    other_last, other_given = name_parts(official_name, last)
    if not last or not given or len(given[0]) < 2 or last != other_last or not other_given:
        return False
    if given[0] != other_given[0] or len(other_given[0]) < 2:
        return False
    return all(a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b))
               for a, b in zip(given[1:], other_given[1:]))


def schedule_name_agrees(grade_name, schedule_name):
    last, given = name_parts(grade_name)
    other_last, other_given = name_parts(schedule_name)
    if not last or not given or not other_given or last != other_last:
        return False
    # A schedule may supply initials or a full first name. A different full
    # first name is not accepted merely because its initial happens to agree.
    return given[0] == other_given[0] or (len(other_given[0]) == 1 and given[0].startswith(other_given[0]))


class DirectoryParser(HTMLParser):
    """Read public faculty headings, staff rows, and Drupal profile cards."""
    def __init__(self, source_url, default_unit=''):
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.unit = default_unit
        self.unit_url = source_url
        self.units = {}
        self.people = []
        self.roster_links = set()
        self.anchor = None
        self.anchor_text = []
        self.pending_profile = None
        self.container_depth = 0
        self.card = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ('div', 'article', 'li'):
            self.container_depth += 1
            classes = attributes.get('class', '').split()
            if 'directory-row' in classes:
                self.pending_profile = None
            if 'profile-card' in classes:
                self.card = {'depth': self.container_depth, 'name_depth': None, 'name': [], 'netids': set(), 'profile_url': None}
            if self.card and any('dircore-display-name' in token for token in classes):
                self.card['name_depth'] = self.container_depth
        href = unescape(attributes.get('href', ''))
        if self.card and href.startswith('mailto:'):
            address = href.removeprefix('mailto:').split('?', 1)[0]
            if address.endswith('@illinois.edu'):
                self.card['netids'].add(address.split('@', 1)[0].casefold())
        if tag == 'a':
            self.anchor = dict(attrs)
            self.anchor_text = []

    def handle_data(self, value):
        if self.anchor is not None:
            self.anchor_text.append(value)
        if self.card and self.card['name_depth'] is not None:
            self.card['name'].append(value)

    def handle_endtag(self, tag):
        if tag in ('div', 'article', 'li'):
            if self.card and self.card['name_depth'] == self.container_depth:
                self.card['name_depth'] = None
            if self.card and self.card['depth'] == self.container_depth:
                name = ' '.join(' '.join(self.card['name']).split())
                if name and len(self.card['netids']) == 1:
                    netid = next(iter(self.card['netids']))
                    self.people.append({'netid': netid, 'name': name, 'unit': self.unit,
                        'unit_url': self.unit_url, 'source_url': self.source_url,
                        'profile_url': self.card['profile_url']})
                self.card = None
            self.container_depth -= 1
        if tag != 'a' or self.anchor is None:
            return
        attrs, self.anchor = self.anchor, None
        href = unescape(attrs.get('href', ''))
        label = ' '.join(' '.join(self.anchor_text).split())
        if not label:
            return
        absolute = urljoin(self.source_url, href)
        query = parse_qs(urlsplit(absolute).query)
        profile_path = re.fullmatch(r'/(?:directory/)?profile/([A-Za-z0-9-]+)/?', urlsplit(absolute).path)
        if (urlsplit(absolute).hostname == urlsplit(self.source_url).hostname
                and urlsplit(absolute).path.startswith('/directory/') and not profile_path
                and '/profile' not in urlsplit(absolute).path
                and not urlsplit(absolute).query):
            self.roster_links.add(absolute.rstrip('/'))
        if query.get('departmentId'):
            self.unit = label
            self.unit_url = 'https://directory.illinois.edu/detail?' + urlencode({'departmentId': query['departmentId'][0]})
            self.units[self.unit_url] = label
            return
        netid = None
        if 'directory-row__link' in attrs.get('class', '').split():
            self.pending_profile = (label, absolute)
            return
        if href.startswith('mailto:') and self.pending_profile:
            address = href.removeprefix('mailto:').split('?', 1)[0]
            if address.endswith('@illinois.edu'):
                netid = address.split('@', 1)[0].casefold()
                name, profile_url = self.pending_profile
                self.people.append({'netid': netid, 'name': name, 'unit': self.unit,
                    'unit_url': self.unit_url, 'source_url': self.source_url, 'profile_url': profile_url})
                self.pending_profile = None
            return
        if query.get('netID') and 'userid' in query.get('search_type', []):
            netid = query['netID'][0].split('@')[0].casefold()
        match = re.fullmatch(r"javascript:goToDetail\('([A-Za-z0-9-]+)'\)", href)
        if match:
            netid = match[1].casefold()
            absolute = self.source_url
        if profile_path:
            if self.card:
                self.card['profile_url'] = absolute
                return
            netid = profile_path[1].casefold()
        if netid:
            self.people.append({'netid': netid, 'name': label, 'unit': self.unit,
                                'unit_url': self.unit_url, 'source_url': self.source_url,
                                'profile_url': absolute if profile_path else None})


class FacultyProfileIndex(HTMLParser):
    def __init__(self, spec):
        super().__init__(convert_charrefs=True)
        self.spec, self.href, self.text = spec, None, []
        self.profiles = {}
        self.page_urls = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href, self.text = dict(attrs).get('href'), []

    def handle_data(self, value):
        if self.href:
            self.text.append(value)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            url = urljoin(self.spec['url'], self.href)
            path = urlsplit(url).path
            name = ' '.join(' '.join(self.text).split())
            if (self.spec.get('page_prefix') and urlsplit(url).hostname == urlsplit(self.spec['url']).hostname
                    and re.fullmatch(re.escape(self.spec['page_prefix']) + r'[1-9]\d*/?', path)
                    and not urlsplit(url).query):
                self.page_urls.add(url)
            if (name and urlsplit(url).hostname == urlsplit(self.spec['url']).hostname
                    and path.startswith(self.spec['profile_prefix'])
                    and path.rstrip('/') != self.spec['profile_prefix'].rstrip('/')
                    and not urlsplit(url).query):
                self.profiles[url] = name
            self.href = None


class GraingerDirectory(HTMLParser):
    """Read each published person card's identifier, name and department."""
    def __init__(self, spec):
        super().__init__(convert_charrefs=True)
        self.spec, self.depth, self.card = spec, 0, None
        self.anchor, self.text, self.people = None, [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div':
            self.depth += 1
            if attrs.get('data-netid') and attrs.get('data-dept'):
                unit = self.spec['units'].get(attrs['data-dept'])
                if unit:
                    self.card = {'depth': self.depth, 'netid': attrs['data-netid'].casefold(), 'unit': unit}
        if tag == 'a' and self.card:
            self.anchor, self.text = attrs.get('href', ''), []

    def handle_data(self, data):
        if self.anchor:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor:
            url = urljoin(self.spec['url'], self.anchor)
            name = ' '.join(' '.join(self.text).split())
            if self.card and urlsplit(url).path.rstrip('/').endswith('/' + self.card['netid']) and name:
                self.card.update(name=name, profile_url=url)
            self.anchor = None
        if tag == 'div':
            if self.card and self.card['depth'] == self.depth:
                if self.card.get('name'):
                    self.people.append({key: self.card[key] for key in ('netid', 'unit', 'name', 'profile_url')}
                        | {'unit_url': self.spec['url'], 'source_url': self.spec['url']})
                self.card = None
            self.depth -= 1


class FacultyProfile(HTMLParser):
    """Bind the profile's own Contact block, excluding assistant contacts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.main, self.contact, self.heading = False, False, None
        self.text, self.names, self.netids = [], [], set()
        self.depth, self.own_contact_depth = 0, None

    def handle_starttag(self, tag, attrs):
        if tag == 'main':
            self.main = True
        if tag == 'div':
            self.depth += 1
            if self.main and 'profile-primary-info__contact-email' in dict(attrs).get('class', '').split():
                self.own_contact_depth = self.depth
        if self.main and tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.heading, self.text = tag, []
        href = dict(attrs).get('href', '')
        if self.main and (self.contact or self.own_contact_depth is not None) and href.startswith('mailto:'):
            address = href.removeprefix('mailto:').split('?', 1)[0]
            if address.endswith('@illinois.edu'):
                identifier = address.split('@', 1)[0].casefold()
                if identifier not in ('law', 'admissions', 'info', 'office', 'webmaster', 'admin'):
                    self.netids.add(identifier)

    def handle_data(self, value):
        if self.heading:
            self.text.append(value)

    def handle_endtag(self, tag):
        if tag == 'div':
            if self.depth == self.own_contact_depth:
                self.own_contact_depth = None
            self.depth -= 1
        if tag == 'main':
            self.main = False
        if tag == self.heading:
            label = ' '.join(' '.join(self.text).split())
            if tag in ('h1', 'h2'):
                self.names.append(label)
            self.contact = label.casefold() in ('contact', 'contact information')
            self.heading = None


class SourceCache:
    def __init__(self, directory, offline=False, pace=1.0):
        self.directory = Path(directory)
        self.offline = offline
        self.pace = pace
        self.last_request = 0
        self.denials_path = self.directory / 'access-denials.json'
        self.denials = read(self.denials_path) if self.denials_path.exists() else {}
        self.blocked_hosts = {host for host, denied_at in self.denials.items()
                              if (datetime.now(timezone.utc) - timestamp(denied_at)).total_seconds() < 86400}

    def path(self, url):
        return self.directory / (digest(url.encode()) + '.json')

    def defer(self, host, denied_at):
        self.blocked_hosts.add(host)
        self.denials.setdefault(host, denied_at)
        atomic_write_json(self.denials_path, self.denials)

    @staticmethod
    def denied(body, status=200):
        return (status in (202, 401, 403, 429)
                or re.search(r'<(?:title|h1)[^>]*>\s*Directory\s+Unavailable', body, re.I) is not None
                or 'off campus access to the directory is currently unavailable' in ' '.join(re.sub('<[^>]+>', ' ', body).lower().split()))

    def fetch(self, url):
        parsed = urlsplit(url)
        official = ((parsed.hostname or '').endswith('.illinois.edu') or
                    parsed.hostname == 'www.trustees.uillinois.edu')
        grade_documentation = parsed.hostname == 'raw.githubusercontent.com' and parsed.path.startswith('/wadefagen/datasets/main/gpa/')
        require(parsed.scheme == 'https' and (official or grade_documentation),
                'Identity sources must use official Illinois HTTPS URLs')
        path = self.path(url)
        if path.exists():
            result = read(path)
            saved_body = base64.b64decode(result['body'], validate=True) if result.get('body_encoding') == 'base64' else result['body'].encode()
            require(result['url'] == url and digest(saved_body) == result.get('body_sha256', result['sha256']),
                    'Identity source cache hash mismatch')
            if self.denied(result['body']):
                self.defer(parsed.hostname, result['fetched_at'])
                raise DataError(f'Saved directory response is access-denied, not an empty directory: {url}')
            return result
        require(not self.offline, f'No saved directory response: {url}')
        require(parsed.hostname not in self.blocked_hosts, f'Source host deferred after access denial: {url}')
        delay = self.pace - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()
        response = subprocess.run([
            'curl', '--silent', '--show-error', '--location', '--max-time', '25',
            '--proto', '=https', '--proto-redir', '=https',
            '--user-agent', 'ProfessorGuide/0.1 (+https://github.com/Illini-Media-Company/professor-guide)',
            '--write-out', '\n%{http_code}\n%{url_effective}', url,
        ], capture_output=True, timeout=30)
        require(response.returncode == 0, f'Directory request failed: {url}: {response.stderr.decode(errors="replace")}')
        body, status, effective_url = response.stdout.rsplit(b'\n', 2)
        status = int(status)
        is_pdf = body.startswith(b'%PDF-')
        text = base64.b64encode(body).decode() if is_pdf else body.decode('utf-8')
        denied = self.denied(text, status)
        if denied:
            self.defer(parsed.hostname, now())
        require(status == 200 and not denied, f'Directory access deferred: HTTP {status}: {url}')
        final_host = urlsplit(effective_url.decode()).hostname or ''
        require(final_host.endswith('.illinois.edu') or final_host == 'www.trustees.uillinois.edu' or
                (grade_documentation and final_host == 'raw.githubusercontent.com'),
                'Directory redirected outside official Illinois sources')
        result = {'url': url, 'fetched_at': now(), 'sha256': digest(body), 'bytes': len(body), 'body': text}
        if is_pdf:
            result['body_encoding'] = 'base64'
        if parsed.hostname in ('directoryapi.wigg.illinois.edu', 'facultysearchapi.itpartners.illinois.edu'):
            result['body'] = json.dumps(minimize_directory_payload(json.loads(text)), ensure_ascii=False)
            result['body_sha256'] = digest(result['body'].encode())
        atomic_write_json(path, result)
        return result


def api_people(payload, spec):
    """Read the public requests used by the college's own directory UI."""
    records = []
    if spec['kind'] == 'wigg_full':
        for office in payload['office']:
            records.extend(office.get('people', []))
    elif spec['kind'] == 'wigg_search':
        require(len(payload['people']) == payload['count'], 'Incomplete public directory response; paginate before reviewing')
        records = payload['people']
    elif spec['kind'] == 'gies':
        require(len(payload['items']) == payload['count'], 'Incomplete public directory response; paginate before reviewing')
        records = payload['items']
    people = []
    for person in records:
        if person.get('isPublished') is False or person.get('published') is False:
            continue
        netid = person.get('netId') or person.get('username')
        name = person.get('fullNameReversed') or person.get('fullname')
        if not netid or not name:
            continue
        units = {person.get('department', ''), person.get('primaryOffice', ''), spec['unit']}
        units.update(job.get('office', '') for job in person.get('jobProfiles', []))
        for unit in units - {''}:
            people.append({'netid': netid.casefold(), 'name': name, 'unit': unit,
                'unit_url': spec['directory_url'], 'source_url': spec['url'],
                'subject_scope': spec['subjects'],
                'directory_url': spec['directory_url'], 'profile_url': person.get('profileUrl') or person.get('externalurlwithpath')})
    return people


def collect_directories(cache, config):
    people, sources, failures = [], {}, []
    units = {}
    for url in (FACULTY_URL, UNITS_URL):
        response = cache.fetch(url)
        parser = DirectoryParser(url)
        parser.feed(response['body'])
        sources[url] = {key: value for key, value in response.items() if key != 'body'}
        units.update(parser.units)
        people.extend(parser.people)
    required_units = {url: unit for url, unit in units.items()
                      if any(any(keyword.casefold() in unit.casefold() for keyword in keywords)
                             for keywords in config['subject_units'].values())}
    targets = [(url, unit) for url, unit in sorted(required_units.items())]
    targets += [(source['url'], source['unit']) for source in config.get('department_rosters', [])]
    visited = set(sources)
    for index, (url, unit) in enumerate(targets, 1):
        if url in visited:
            continue
        visited.add(url)
        try:
            response = cache.fetch(url)
            parser = DirectoryParser(url, unit)
            parser.feed(response['body'])
            people.extend(parser.people)
            sources[url] = {key: value for key, value in response.items() if key != 'body'}
            sources[url]['parsed_people'] = len(parser.people)
            sources[url]['unit'] = unit
            targets.extend((link, unit) for link in sorted(parser.roster_links) if link not in visited)
            print(f'Directory {index}/{len(targets)}: {unit}: {len(parser.people)} people', flush=True)
        except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            failures.append({'url': url, 'unit': unit, 'reason': str(error)})
            print(f'Directory deferred: {unit}: {error}', flush=True)
    for variant in config.get('reviewed_name_variants', []):
        for url in variant['source_urls']:
            if url not in sources:
                try:
                    response = cache.fetch(url)
                    sources[url] = {key: value for key, value in response.items() if key != 'body'}
                except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                    failures.append({'url': url, 'unit': 'Reviewed name-variant evidence', 'reason': str(error)})
    for spec in config.get('api_rosters', []):
        try:
            for url in (spec['directory_url'], spec['url']):
                response = cache.fetch(url)
                sources[url] = {key: value for key, value in response.items() if key != 'body'}
            parsed = api_people(json.loads(response['body']), spec)
            people.extend(parsed)
            sources[spec['url']]['unit'] = spec['unit']
            sources[spec['url']]['parsed_people'] = len(parsed)
            print(f"Public directory API: {spec['unit']}: {len({p['netid'] for p in parsed})} people", flush=True)
        except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            failures.append({'url': spec['url'], 'unit': spec['unit'], 'reason': str(error)})
    for spec in config.get('grainger_rosters', []):
        try:
            response = cache.fetch(spec['url'])
            parser = GraingerDirectory(spec)
            parser.feed(response['body'])
            require(parser.people, 'Official engineering directory contains no recognized person cards')
            people.extend(parser.people)
            sources[spec['url']] = {key: value for key, value in response.items() if key != 'body'}
            sources[spec['url']]['parsed_people'] = len(parser.people)
            print(f"Engineering directory: {len(parser.people)} people", flush=True)
        except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            failures.append({'url': spec['url'], 'unit': 'Grainger College of Engineering', 'reason': str(error)})
    for spec in config.get('manual_directory_people', []):
        require(spec['reviewed_by'] and spec['evidence'] and spec['source_urls'], 'Manual identity needs explicit source review')
        timestamp(spec['reviewed_at'])
        profile_url = spec.get('profile_url')
        if spec['directory_id'].startswith('profile_'):
            require(profile_url and spec['directory_id'] == 'profile_' + digest(profile_url.encode())[:24],
                    'Manual profile identity must use its reviewed URI hash')
            parsed_profile = urlsplit(profile_url)
            require(parsed_profile.scheme == 'https' and (parsed_profile.hostname or '').endswith('.illinois.edu'),
                    'Manual profile identity needs an official Illinois URI')
        available = True
        for url in spec['source_urls']:
            if url not in sources:
                try:
                    response = cache.fetch(url)
                    sources[url] = {key: value for key, value in response.items() if key != 'body'}
                except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                    failures.append({'url': url, 'unit': spec['unit'], 'reason': str(error)})
                    available = False
        if available:
            for url in spec['source_urls']:
                people.append({'netid': spec['directory_id'], 'name': spec['official_name'],
                    'unit': spec['unit'], 'unit_url': url, 'source_url': url,
                    'subject_scope': spec['subjects'], 'profile_url': profile_url,
                    'manual_review': spec,
                    'faculty_directory_urls': [spec['directory_url']] if spec.get('directory_url') else []})
    grade_names = config.get('_grade_names', [])
    for spec in config.get('profile_indexes', []):
        try:
            response = cache.fetch(spec['url'])
            sources[spec['url']] = {key: value for key, value in response.items() if key != 'body'}
            index = FacultyProfileIndex(spec)
            index.feed(response['body'])
            pages, visited_pages = sorted(index.page_urls), {spec['url']}
            while pages:
                page_url = pages.pop(0)
                if page_url in visited_pages:
                    continue
                visited_pages.add(page_url)
                require(len(visited_pages) <= 100, 'Unexpected directory pagination size')
                try:
                    response = cache.fetch(page_url)
                    page = FacultyProfileIndex(spec)
                    page.feed(response['body'])
                    sources[page_url] = {key: value for key, value in response.items() if key != 'body'}
                    index.profiles.update(page.profiles)
                    pages.extend(sorted(page.page_urls - visited_pages))
                except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                    failures.append({'url': page_url, 'unit': spec['unit'], 'reason': str(error)})
            targets = {url: name for url, name in index.profiles.items()
                       if any(full_name_agrees(grade_name, name) for grade_name in grade_names)}
            for number, (url, name) in enumerate(sorted(targets.items()), 1):
                try:
                    response = cache.fetch(url)
                    profile = FacultyProfile()
                    profile.feed(response['body'])
                    require(any(full_name_agrees(grade_name, actual) for grade_name in grade_names
                                if full_name_agrees(grade_name, name) for actual in profile.names[:1]),
                            'Faculty profile title does not confirm its directory name')
                    sources[url] = {key: value for key, value in response.items() if key != 'body'}
                    identifier = next(iter(profile.netids)) if len(profile.netids) == 1 else 'profile_' + digest(url.encode())[:24]
                    people.append({'netid': identifier, 'name': name, 'unit': spec['unit'],
                        'unit_url': spec['url'], 'source_url': url, 'directory_url': spec['url'],
                        'subject_scope': spec['subjects'], 'profile_url': url,
                        'faculty_directory_urls': [url]})
                    print(f"Faculty profile {number}/{len(targets)}: {name}", flush=True)
                except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                    failures.append({'url': url, 'unit': spec['unit'], 'reason': str(error)})
        except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            failures.append({'url': spec['url'], 'unit': spec['unit'], 'reason': str(error)})
    config['_subject_unit_sources'] = {}
    for subject, review in config.get('subject_unit_reviews', {}).items():
        require(review['reviewed_by'] and review['evidence'] and review['source_urls'] and review['added_units'],
                'Reviewed subject affiliation needs explicit evidence')
        timestamp(review['reviewed_at'])
        require(set(review['added_units']) <= set(config['subject_units'].get(subject, [])),
                'Reviewed subject affiliation disagrees with configured units')
        available = True
        for url in review['source_urls']:
            try:
                response = cache.fetch(url)
                sources[url] = {key: value for key, value in response.items() if key != 'body'}
            except (DataError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                failures.append({'url': url, 'unit': subject, 'reason': str(error)})
                available = False
        if available:
            config['_subject_unit_sources'][subject] = review['source_urls']
        else:
            config['subject_units'][subject] = [unit for unit in config['subject_units'][subject]
                                                if unit not in review['added_units']]
    return people, sources, failures


def variant_schedule_name(variant, grade_name):
    official = variant.get('schedule_identity_name', variant['official_name'])
    if ',' in official:
        return official
    last, given = name_parts(official, name_parts(grade_name)[0])
    require(last and given, 'Reviewed natural-name variant needs an explicit schedule_identity_name')
    return ' '.join(last) + ', ' + ' '.join(given)


def schedule_index(public_dir):
    manifest_path = Path(public_dir) / 'integration.json'
    manifest = read(manifest_path)
    history = read_object(public_dir, manifest['files']['history'])
    listings, archive, sources = defaultdict(list), defaultdict(list), {}
    for row in history['coverage']['terms']:
        if row['status'] != 'collected':
            continue
        snapshot = validate_snapshot(read_object(public_dir, row['snapshot']))
        sources.update({item['url']: item['fetched_at'] for item in snapshot['sources']})
        for section in snapshot['sections']:
            subject = section['course_code'].split()[0]
            for meeting in section['meetings']:
                for index, person in enumerate(meeting['instructors']):
                    occurrence = {'listing_id': section['listing_id'], 'section_id': section['id'],
                                  'meeting_id': meeting['id'], 'instructor_index': index,
                                  'name_raw': person['name_raw'],
                                  'source_url': section.get('response_source_url', section['source_url']),
                                  'fetched_at': section['collected_at']}
                    listings[section['listing_id']].append(occurrence)
                    archive[(subject, person['name_raw'])].append(occurrence)
    return listings, archive, digest(manifest_path.read_bytes()), sources


@lru_cache(maxsize=8192)
def unit_tokens(value):
    result = words(value.replace('&', ' and '))
    if result[-3:] in (['department', 'of', 'the'], ['school', 'of', 'the'], ['college', 'of', 'the']):
        result = result[:-3]
    if result[:2] in (['department', 'of'], ['school', 'of'], ['college', 'of']):
        result = result[2:]
    if result[-2:] in (['department', 'of'], ['school', 'of'], ['college', 'of']):
        result = result[:-2]
    if result and result[-1] in ('department', 'school', 'college'):
        result = result[:-1]
    return tuple(result)


def unit_agrees(subject, person, config):
    if person.get('subject_scope') is not None and subject not in person['subject_scope']:
        return False
    unit = unit_tokens(person['unit'])
    return any(unit[:len(unit_tokens(keyword))] == unit_tokens(keyword) for keyword in config['subject_units'].get(subject, []))


def people_indexes(people, config):
    by_name = defaultdict(list)
    by_initial = defaultdict(dict)
    for person in people:
        if ',' in person['name']:
            parts = [name_parts(person['name'])]
        else:
            tokens = words(person['name'])
            while tokens and tokens[0] in ('dr', 'prof', 'professor'):
                tokens.pop(0)
            while tokens and tokens[-1] in ('phd', 'md'):
                tokens.pop()
            parts = [(tokens[cut:], tokens[:cut]) for cut in range(1, len(tokens))]
        subjects = [subject for subject in config['subject_units'] if unit_agrees(subject, person, config)]
        for last, given in parts:
            if not last or not given:
                continue
            by_name[(tuple(last), given[0])].append(person)
            for subject in subjects:
                by_initial[(subject, tuple(last), given[0][0])].setdefault(person['netid'], person)
    return by_name, by_initial


def review_inventory(grades, people, listings, config, reviewed_at):
    grouped = defaultdict(list)
    for grade in grades:
        grouped[grade.get('primary_instructor_name_raw') or ''].append(grade)
    by_name, by_initial = people_indexes(people, config)
    variants = {variant['grade_name_raw']: variant for variant in config.get('reviewed_name_variants', [])}
    candidate_rows = {}
    source_names = defaultdict(set)
    source_identities = defaultdict(set)
    for name, rows in grouped.items():
        last, given = name_parts(name)
        subjects = {row['course_code'].split()[0] for row in rows}
        possible = by_name.get((tuple(last), given[0]), []) if given else []
        candidates = [p for p in possible if full_name_agrees(name, p['name'])
                      and any(unit_agrees(subject, p, config) for subject in subjects)]
        variant = variants.get(name)
        if variant:
            require(variant['reviewed_by'] and variant['evidence'] and variant['source_urls'], 'Name variant requires explicit review evidence')
            timestamp(variant['reviewed_at'])
            candidates = [p for p in people if p['netid'] == variant['directory_id']
                          and p['name'] == variant['official_name']
                          and any(unit_agrees(subject, p, config) for subject in subjects)]
            last, given = name_parts(variant_schedule_name(variant, name))
        candidate_rows[name] = candidates
        ids = {p['netid'] for p in candidates}
        identity_key = 'id:' + next(iter(ids)) if len(ids) == 1 else 'source:' + ' '.join(words(name))
        if last and given:
            for subject in subjects:
                key = (subject, tuple(last), given[0][0])
                source_names[key].add(name)
                source_identities[key].add(identity_key)
    names_by_id = defaultdict(set)
    for name, candidates in candidate_rows.items():
        ids = {person['netid'] for person in candidates}
        if len(ids) == 1:
            names_by_id[next(iter(ids))].add(name)
    conflicting_ids = set()
    for identifier, names in names_by_id.items():
        canonical = [variant_schedule_name(variants[name], name) if name in variants else name for name in sorted(names)]
        if any(not full_name_agrees(left, right) for i, left in enumerate(canonical) for right in canonical[i + 1:]):
            conflicting_ids.add(identifier)
    identities = []
    for name, rows in sorted(grouped.items()):
        subjects = sorted({row['course_code'].split()[0] for row in rows})
        candidates = candidate_rows[name]
        variant = variants.get(name)
        by_id = defaultdict(list)
        for candidate in candidates:
            by_id[candidate['netid']].append(candidate)
        entry = {'grade_name_raw': name, 'grade_record_count': len(rows), 'subjects': subjects,
                 'checked_at': reviewed_at, 'reviewed_by': 'Codex (official directory and schedule context)',
                 'status': 'needs_review', 'candidates': [], 'matched_grades': [], 'unresolved_grades': []}
        for netid, evidence in sorted(by_id.items()):
            entry['candidates'].append({'netid': netid,
                'official_names': sorted({p['name'] for p in evidence}),
                'units': sorted({p['unit'] for p in evidence}),
                'source_urls': sorted({url for p in evidence for url in (p['source_url'], p.get('directory_url', p['source_url']))}),
                'faculty_directory_urls': sorted({url for p in evidence
                    for url in p.get('faculty_directory_urls', [p.get('directory_url', p['source_url'])])}),
                'profile_urls': sorted({p['profile_url'] for p in evidence if p['profile_url']})})
        for candidate in entry['candidates']:
            for subject in subjects:
                review = config.get('subject_unit_reviews', {}).get(subject)
                if review and subject in config.get('_subject_unit_sources', {}) and any(
                        unit_tokens(unit) == unit_tokens(added) for unit in candidate['units'] for added in review['added_units']):
                    candidate['source_urls'] = sorted(set(candidate['source_urls']) | set(config['_subject_unit_sources'][subject]))
        if len(by_id) != 1 or next(iter(by_id), None) in conflicting_ids:
            entry['reason'] = ('no_full_name_and_department_match' if not by_id else
                              'conflicting_names_for_official_identity' if len(by_id) == 1 else 'multiple_official_identities')
            if entry['reason'] == 'conflicting_names_for_official_identity':
                entry['conflicting_grade_names'] = sorted(names_by_id[next(iter(by_id))])
            entry['unresolved_grades'] = [{'grade_record_id': row['id'], 'reason': entry['reason']} for row in rows]
            identities.append(entry)
            continue
        netid, evidence = next(iter(by_id.items()))
        entry.update(status='verified_identity', netid=netid, reason='unique_official_full_name_and_department')
        if variant:
            entry['reason'] = 'reviewed_source_name_variant'
            entry['name_variant_review'] = variant
            entry['candidates'][0]['source_urls'] = sorted(set(entry['candidates'][0]['source_urls']) | set(variant['source_urls']))
            entry['candidates'][0]['faculty_directory_urls'] = sorted(set(entry['candidates'][0]['faculty_directory_urls']) | set(variant.get('faculty_profile_urls', [])))
        for row in rows:
            if row['grain'] == 'course_term':
                entry['unresolved_grades'].append({'grade_record_id': row['id'], 'reason': 'course_term_aggregate'})
                continue
            subject = row['course_code'].split()[0]
            listing_id = f"{row['term_id']}:{row['course_code']}"
            if not any(unit_agrees(subject, p, config) for p in evidence):
                entry['unresolved_grades'].append({'grade_record_id': row['id'], 'reason': 'department_not_verified_for_this_subject'})
                continue
            source_name = variant_schedule_name(variant, name) if variant else name
            occurrences = [p for p in listings.get(listing_id, []) if schedule_name_agrees(source_name, p['name_raw'])]
            if row['grain'] == 'section':
                occurrences = [p for p in occurrences if p['section_id'] == row['section_id']]
            # A second directory person with this surname/initial prevents an
            # initials-only occurrence from being assigned to the full name.
            collision_last, collision_given = name_parts(source_name)
            collisions = set(by_initial.get((subject, tuple(collision_last), collision_given[0][0]), {})) - {netid}
            source_key = (subject, tuple(collision_last), collision_given[0][0])
            if len(source_identities[source_key]) > 1:
                entry['unresolved_grades'].append({'grade_record_id': row['id'],
                    'reason': 'ambiguous_grade_source_names',
                    'conflicting_grade_names': sorted(source_names[source_key])})
                continue
            if not occurrences or collisions:
                entry['unresolved_grades'].append({'grade_record_id': row['id'],
                    'reason': 'ambiguous_schedule_initials' if collisions else 'no_matching_schedule_occurrence',
                    **({'conflicting_netids': sorted(collisions)} if collisions else {})})
                continue
            occurrence = min(occurrences, key=lambda p: (p['section_id'], p['meeting_id'], p['instructor_index']))
            entry['matched_grades'].append({'grade_record_id': row['id'], 'occurrence': occurrence})
        identities.append(entry)
    return identities


def validate_review_inventory(grades, identities):
    """Every raw label and grade row must have exactly one recorded outcome."""
    by_id = {grade['id']: grade for grade in grades}
    require(len(by_id) == len(grades), 'Duplicate GPA IDs in identity review')
    expected = Counter(grade.get('primary_instructor_name_raw') or '' for grade in grades)
    require(Counter(entry['grade_name_raw'] for entry in identities) == Counter({name: 1 for name in expected}),
            'Identity review must account for every GPA source name once')
    seen = []
    for entry in identities:
        outcomes = entry['matched_grades'] + entry['unresolved_grades']
        require(len(outcomes) == entry['grade_record_count'] == expected[entry['grade_name_raw']],
                'Identity review grade count mismatch')
        require(not entry['matched_grades'] or entry['status'] == 'verified_identity',
                'Unverified identity cannot have accepted grade rows')
        for outcome in outcomes:
            grade_id = outcome['grade_record_id']
            require(grade_id in by_id and (by_id[grade_id].get('primary_instructor_name_raw') or '') == entry['grade_name_raw'],
                    'Identity review row belongs to a different source name')
            seen.append(grade_id)
    require(Counter(seen) == Counter({grade_id: 1 for grade_id in by_id}),
            'Identity review must account for every GPA row once')


def review_archive_names(archive, people, config, identities, links):
    """Account for every source label, retaining uncertainty in initials."""
    _, by_initial = people_indexes(people, config)
    existing = {(link['section_id'], link['meeting_id'], link['instructor_index'], link['name_raw'], link['listing_id'])
                for link in links['records'] if link['verified'] is True}
    supported = defaultdict(set)
    grade_names = defaultdict(set)
    for entry in identities:
        grade_name = (variant_schedule_name(entry['name_variant_review'], entry['grade_name_raw'])
                      if entry.get('name_variant_review') else entry['grade_name_raw'])
        last, given = name_parts(grade_name)
        if last and given:
            for subject in entry['subjects']:
                grade_names[(subject, tuple(last), given[0][0])].add(entry['grade_name_raw'])
        for match in entry['matched_grades']:
            occurrence = match['occurrence']
            subject = occurrence['listing_id'].split(':', 1)[1].split()[0]
            supported[(subject, occurrence['name_raw'])].add(entry['netid'])
    reviews = []
    for (subject, name), occurrences in sorted(archive.items()):
        last, given = name_parts(name)
        grade_candidates = grade_names.get((subject, tuple(last), given[0][0]), set()) if given else set()
        possible = by_initial.get((subject, tuple(last), given[0][0]), {}) if given else {}
        if given and len(given[0]) > 1:
            possible = {key: person for key, person in possible.items() if full_name_agrees(name, person['name'])}
        verified_count = sum((o['section_id'], o['meeting_id'], o['instructor_index'], o['name_raw'], o['listing_id']) in existing for o in occurrences)
        if verified_count == len(occurrences):
            status = 'verified_occurrences'
        elif verified_count:
            status = 'partially_verified_occurrences'
        elif len(possible) > 1:
            status = 'ambiguous_directory_identities'
        elif possible:
            status = 'candidate_requires_occurrence_review'
        else:
            status = 'needs_additional_source_evidence'
        reviews.append({'subject': subject, 'name_raw': name, 'occurrence_count': len(occurrences),
            'verified_occurrence_count': verified_count, 'status': status,
            'review_scope': 'gpa_context' if grade_candidates else 'archive_only_label',
            'gpa_source_name_candidates': sorted(grade_candidates),
            'grade_supported_directory_ids': sorted(supported[(subject, name)]),
            'candidates': [{'directory_id': key, 'official_name': person['name'],
                            'source_url': person['source_url']} for key, person in sorted(possible.items())]})
    return reviews


def write_review_report(ledger):
    summary = ledger['summary']
    reasons = Counter(row['reason'] for entry in ledger['identities'] for row in entry['unresolved_grades'])
    lines = ['# Identity review coverage', '', f"Review run: `{ledger['reviewed_at']}`.",
        '', f"All **{summary['grade_name_labels']:,} GPA source-name labels** and **{summary['gpa_rows']:,} grade rows** were evaluated against the saved official directory sources and the campus archive.",
        f"**{summary['verified_directory_ids']:,} distinct directory identities** have supporting full-name and department evidence. {summary['reviewed_grade_rows']:,} grade rows have a reviewed course/term occurrence; {summary['unresolved_grade_rows']:,} require further evidence.",
        '', 'Names with incomplete, conflicting, or unavailable evidence stay unresolved. Public source access failures are recorded in the ledger. Current rosters may omit former instructors.',
        '', '## GPA outcomes', '', '| Grade-row outcome | Rows |', '| --- | ---: |']
    for reason, count in reasons.most_common():
        lines.append(f'| {reason} | {count:,} |')
    if ledger.get('archive_name_reviews') is not None:
        counts = Counter(row['status'] for row in ledger['archive_name_reviews'])
        scopes = Counter(row['review_scope'] for row in ledger['archive_name_reviews'])
        lines += ['', '## Archive source-name outcomes', '',
                  'Each row is a subject/name label; abbreviated labels are not counts of unique people. Grade-backed reviews are retained separately from unverified historical occurrences.',
                  f"{scopes['archive_only_label']:,} labels have no matching GPA surname/initial in that subject. The other {scopes['gpa_context']:,} have possible GPA context; initials alone do not verify a shared identity.",
                  '', '| Outcome | Subject/name labels |', '| --- | ---: |']
        lines += [f'| {status} | {count:,} |' for status, count in counts.most_common()]
    lines += ['', '## Follow-up queue', '', '| GPA source name | Rows | Subjects | Reason |', '| --- | ---: | --- | --- |']
    pending = sorted((entry for entry in ledger['identities'] if entry['status'] == 'needs_review'),
                     key=lambda entry: (-entry['grade_record_count'], entry['grade_name_raw']))
    for entry in pending[:30]:
        lines.append(f"| {entry['grade_name_raw']} | {entry['grade_record_count']} | {', '.join(entry['subjects'])} | {entry['reason']} |")
    lines += ['', 'The complete [GPA queue](../data/mappings/identity-review.csv) includes every source label. The [archive queue](../data/mappings/archive-identity-review.csv) includes every subject/name pair. The [review ledger](../data/mappings/professor-identities.json) records row-level decisions, directory IDs, source URLs/hashes/timestamps, and input fingerprints.',
        '', 'Reproduce with saved source responses: `python3 -m scripts.review_identities --reuse-sources --include-archive`. Use `--apply` to export accepted evidence-backed decisions to normalized inputs. These commands do not publish or deploy.', '']
    atomic_write_text('docs/identity-review-coverage.md', '\n'.join(lines))
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['grade_name_raw', 'status', 'directory_id', 'grade_rows', 'matched_grade_rows',
                     'unresolved_grade_rows', 'subjects', 'reason', 'unresolved_reasons', 'official_sources'])
    for entry in ledger['identities']:
        writer.writerow([entry['grade_name_raw'], entry['status'], entry.get('netid', ''),
            entry['grade_record_count'], len(entry['matched_grades']), len(entry['unresolved_grades']),
            '; '.join(entry['subjects']), entry['reason'], '; '.join(sorted({row['reason'] for row in entry['unresolved_grades']})),
            '; '.join(sorted({url for candidate in entry['candidates'] for url in candidate['source_urls']}))])
    atomic_write_text('data/mappings/identity-review.csv', output.getvalue())
    if ledger.get('archive_name_reviews') is not None:
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['subject', 'name_raw', 'review_scope', 'status', 'occurrences', 'verified_occurrences',
                         'gpa_source_name_candidates', 'candidate_directory_ids', 'grade_supported_directory_ids'])
        for entry in ledger['archive_name_reviews']:
            writer.writerow([entry['subject'], entry['name_raw'], entry['review_scope'], entry['status'],
                entry['occurrence_count'], entry['verified_occurrence_count'], '; '.join(entry['gpa_source_name_candidates']),
                '; '.join(candidate['directory_id'] for candidate in entry['candidates']),
                '; '.join(entry['grade_supported_directory_ids'])])
        atomic_write_text('data/mappings/archive-identity-review.csv', output.getvalue())


def export_reviews(ledger, gpa, professors, links):
    """Add only ledger-verified identities and their independently scoped rows."""
    require(len(gpa['sources']) == 1, 'Bulk review export requires one unambiguous GPA source')
    # Rebuild this batch's generated bridges so newly discovered conflicts
    # remove stale decisions. Independently authored reviews remain intact.
    retained = []
    for link in links['records']:
        matches = link.get('grade_name_matches', [])
        kept = [match for match in matches if match.get('reviewed_by') != 'Codex (official directory and schedule context)']
        if len(kept) != len(matches):
            link['grade_name_matches'] = kept
        generated = link.get('review_method') == REVIEW_METHOD or (
            link['id'].startswith('link_') and any(text.startswith('Reviewed against the official Illinois identity ') for text in link['evidence']))
        if not generated or kept or link['is_primary']:
            retained.append(link)
    links['records'] = retained
    accepted_ids = {entry['netid'] for entry in ledger['identities'] if entry['status'] == 'verified_identity'}
    independently_linked = {link['professor_id'] for link in retained}
    def directory_key(person):
        if person.get('directory_profile_url'):
            return 'profile_' + digest(person['directory_profile_url'].encode())[:24]
        return person.get('institutional_id')
    professors['records'] = [person for person in professors['records']
        if not person['professor_id'].startswith('prof_uiuc_')
        or person.get('identity_source') == 'official_faculty_directory'
        or directory_key(person) in accepted_ids
        or person['professor_id'] in independently_linked]
    grades = {grade['id']: grade for grade in gpa['records']}
    people_by_netid = {directory_key(p): p for p in professors['records'] if directory_key(p)}
    for person in professors['records']:
        for link in person.get('faculty_links', []):
            path = urlsplit(link['url']).path
            if '/directory/profile/' in path:
                people_by_netid.setdefault(path.rstrip('/').rsplit('/', 1)[-1], person)
    occurrences = {(p['section_id'], p['meeting_id'], p['instructor_index'], p['professor_id']): p for p in links['records']}
    source_times = {source['url']: source['fetched_at'] for source in links['sources']}
    professor_sources = {source['url']: source['fetched_at'] for source in professors['sources']}
    source_times.update({source['url']: source['fetched_at'] for source in gpa['sources']})
    for entry in ledger['identities']:
        if entry['status'] != 'verified_identity':
            continue
        netid = entry['netid']
        candidate = entry['candidates'][0]
        for url in candidate['source_urls']:
            source_times[url] = professor_sources[url] = ledger['sources'][url]['fetched_at']
        person = people_by_netid.get(netid)
        official = candidate['official_names'][0]
        identity_evidence = [
            f"Official Illinois sources identify {official} (review key {netid}) in {', '.join(candidate['units'])}.",
            ("Explicit source-name variant review: " + ' '.join(entry['name_variant_review']['evidence'])
             if entry.get('name_variant_review') else
             f"Reviewed the GPA name {entry['grade_name_raw']} using full first/surname, compatible supplied middle names, and department evidence; initials alone were not used to establish identity.")]
        if person is None:
            if ',' in official:
                last, given = official.split(',', 1)
                display_name = given.strip() + ' ' + last.strip()
            else:
                display_name = official
            person = {'professor_id': 'prof_uiuc_' + netid,
                      'display_name': display_name,
                      'identity_evidence': identity_evidence,
                      'faculty_links': [{'url': url,
                          'evidence': f'Official unit directory lists {official} with university identity {netid}.',
                          'verified_at': ledger['sources'][url]['fetched_at']}
                          for url in candidate.get('faculty_directory_urls', candidate['source_urls'])], 'rmp': None}
            professors['records'].append(person)
            people_by_netid[netid] = person
        elif person['professor_id'] == 'prof_uiuc_' + netid:
            person['identity_evidence'] = identity_evidence
        if netid.startswith('profile_'):
            person.setdefault('directory_profile_url', candidate['profile_urls'][0])
        else:
            person.setdefault('institutional_id', netid)
        for match in entry['matched_grades']:
            grade = grades[match['grade_record_id']]
            occurrence = match['occurrence']
            key = (occurrence['section_id'], occurrence['meeting_id'], occurrence['instructor_index'], person['professor_id'])
            link = occurrences.get(key)
            if link is not None:
                require(all(link[field] == occurrence[field] for field in ('listing_id', 'name_raw')),
                        'Existing occurrence review disagrees with the saved source')
            if link is None:
                link = {field: occurrence[field] for field in ('section_id', 'listing_id', 'meeting_id', 'instructor_index', 'name_raw')}
                link.update(id='link_' + digest((':'.join(map(str, key))).encode())[:24],
                            professor_id=person['professor_id'], verified=True, verified_at=ledger['reviewed_at'],
                            review_method=REVIEW_METHOD,
                            evidence=[f"Reviewed against the official Illinois identity {netid} and the preserved occurrence in {occurrence['listing_id']}; department and full grade-source name agree."],
                            is_primary=False, primary_evidence=[], grade_name_matches=[])
                links['records'].append(link)
                occurrences[key] = link
            if not any(item['grade_record_id'] == grade['id'] for item in link.get('grade_name_matches', [])):
                link.setdefault('grade_name_matches', []).append({
                    'grade_record_id': grade['id'], 'primary_instructor_name_raw': grade['primary_instructor_name_raw'],
                    'source_url': gpa['sources'][0]['url'], 'reviewed_by': entry['reviewed_by'],
                    'verified_at': ledger['reviewed_at'],
                    'evidence': [f"Full-name and department review connects {entry['grade_name_raw']} to official Illinois identity {netid} and this course/term occurrence.",
                                 'Official evidence: ' + ', '.join(candidate['source_urls'])],
                    'primary_evidence': [f"The grade source explicitly names {grade['primary_instructor_name_raw']} in Primary Instructor for {grade['course_code']} ({grade['term_id']}); this review applies only to this source row.",
                                         'The source retains its actual section ID.' if grade['grain'] == 'section' else
                                         'No section-primary designation or CRN is inferred from this instructor/course/term grade.']})
            source_times[occurrence['source_url']] = occurrence['fetched_at']
    for data, sources, kind in ((professors, professor_sources, 'professors'), (links, source_times, 'verified_occurrences')):
        data['sources'] = [{'url': url, 'fetched_at': fetched} for url, fetched in sorted(sources.items())]
        data['collected_at'] = max(sources.values(), key=timestamp)
        validate_input(data, kind)
    return professors, links


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('config/identity-review.json'))
    parser.add_argument('--cache-dir', type=Path, default=Path('.cache/identity-review'))
    parser.add_argument('--reuse-sources', action='store_true', help='Use only saved official-directory responses')
    parser.add_argument('--apply', action='store_true', help='Export verified ledger decisions to normalized inputs')
    parser.add_argument('--include-archive', action='store_true', help='After GPA review, inventory all archive subject/name labels')
    args = parser.parse_args()
    config = read(args.config)
    config['_grade_names'] = sorted({grade.get('primary_instructor_name_raw') or '' for grade in read('data/inputs/gpa.json')['records']})
    people, sources, failures = collect_directories(SourceCache(args.cache_dir, args.reuse_sources), config)
    config['reviewed_name_variants'] = [variant for variant in config.get('reviewed_name_variants', [])
                                       if all(url in sources for url in variant['source_urls'])]
    listings, archive, manifest_hash, _ = schedule_index('public/data')
    gpa_path = Path('data/inputs/gpa.json')
    gpa = validate_input(read(gpa_path), 'gpa')
    reviewed_at = now()
    identities = review_inventory(gpa['records'], people, listings, config, reviewed_at)
    validate_review_inventory(gpa['records'], identities)
    counts = Counter(entry['status'] for entry in identities)
    ledger = {'schema_version': 1, 'status': 'review_in_progress', 'reviewed_at': reviewed_at,
              'scope': 'all GPA source-name labels first; archive-only names follow',
              'review_method': REVIEW_METHOD,
              'inputs': {'gpa_sha256': digest(gpa_path.read_bytes()), 'manifest_sha256': manifest_hash,
                         'config_sha256': digest(args.config.read_bytes()),
                         'review_script_sha256': digest(Path(__file__).read_bytes())},
              'sources': sources, 'source_failures': failures,
              'summary': {'gpa_rows': len(gpa['records']), 'grade_name_labels': len(identities),
                          'identities_by_status': dict(counts),
                          'verified_directory_ids': len({entry['netid'] for entry in identities if entry['status'] == 'verified_identity'}),
                          'reviewed_grade_rows': sum(len(p['matched_grades']) for p in identities),
                          'unresolved_grade_rows': sum(len(p['unresolved_grades']) for p in identities),
                          'archive_subject_name_pairs': len(archive)},
              'identities': identities}
    professors, links = read('data/inputs/professors.json'), read('data/inputs/verified-links.json')
    if args.apply:
        professors, links = export_reviews(ledger, gpa, professors, links)
        # Validate all new joins before either normalized input is replaced.
        from scripts.integration import attribute_grades, validate_bundle
        _, saved = validate_bundle('public/data')
        attribute_grades(saved['schedule'], saved['history'], {'gpa': gpa, 'professors': professors, 'verified_occurrences': links})
        atomic_write_json('data/inputs/professors.json', professors)
        atomic_write_json('data/inputs/verified-links.json', links)
    if args.include_archive:
        ledger['archive_name_reviews'] = review_archive_names(archive, people, config, identities, links)
    atomic_write_json('data/mappings/professor-identities.json', ledger)
    write_review_report(ledger)
    print(json.dumps(ledger['summary'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
