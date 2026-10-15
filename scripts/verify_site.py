"""Verify deployed HTML, assets, manifest, and every immutable JSON file hash."""

import argparse
import hashlib
from html.parser import HTMLParser
import json
import ssl
import time
from urllib.parse import urljoin
from urllib.request import urlopen

import certifi


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'script' and values.get('src'): self.paths.append(values['src'])
        if tag == 'link' and values.get('rel') == 'stylesheet': self.paths.append(values['href'])


def verify(url, expected_manifest=None, expected_sha256=None):
    def get(relative):
        with urlopen(urljoin(url,relative), timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as response:
            assert response.status == 200
            return response.read()
    parser = Assets()
    parser.feed(get('').decode())
    assert parser.paths, 'No built assets'
    for asset in parser.paths: assert get(asset)
    manifest_body = get('data/integration.json')
    if expected_sha256:
        assert hashlib.sha256(manifest_body).hexdigest() == expected_sha256, 'Deployed manifest is not this revision yet'
    manifest = json.loads(manifest_body)
    if expected_manifest:
        assert manifest == json.loads(open(expected_manifest,encoding='utf-8').read()), 'Deployed manifest is not this revision yet'
    checked = {}
    def check(item):
        if item['path'] in checked:
            assert checked[item['path']] == (item['sha256'], item['bytes'])
            return None
        assert item['path'] == 'objects/' + item['sha256'] + '.json', 'Unsafe hash path'
        body = get('data/' + item['path'])
        assert hashlib.sha256(body).hexdigest() == item['sha256'], 'Deployed hash mismatch'
        assert len(body) == item['bytes']
        checked[item['path']] = item['sha256'], item['bytes']
        return body
    for name, item in manifest['files'].items():
        if item['status'] == 'available':
            body = check(item)
            if name == 'history':
                history = json.loads(body)
                if history['schema_version'] == 2:
                    for row in history['coverage']['terms']:
                        if row['status'] == 'collected':
                            check(row['snapshot'])
                            check(row['department_coverage'])
    count = len(checked)
    assert get('embed-test.html')
    print(f'Verified {url}: HTML, {len(parser.paths)} assets, {count} JSON hashes, and embed test page.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--expected-manifest')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    for attempt in range(6):
        try:
            verify(args.url,args.expected_manifest,args.expected_sha256)
            break
        except Exception:
            if attempt == 5: raise
            time.sleep(10)
