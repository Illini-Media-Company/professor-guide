"""Exercise the durable, cache-free integration path in an isolated source tree."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class FreshCheckoutTests(unittest.TestCase):
    def test_without_local_snapshots_caches_or_certificate_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree('scripts',root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree('config',root/'config')
            shutil.copytree('public/data',root/'public/data')
            shutil.copytree('data/mappings',root/'data/mappings')
            (root/'docs').mkdir()
            before = (root/'public/data/integration.json').read_bytes()
            environment = dict(os.environ)
            environment.pop('SSL_CERT_FILE',None)
            term = json.loads((root/'config/collection.json').read_text())['current_term']
            result = subprocess.run([sys.executable,'-m','scripts.update_data','--reuse-current','--term',term],cwd=root,env=environment,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('0 network requests',result.stdout)
            self.assertFalse((root/'.cache').exists())
            self.assertEqual((root/'public/data/integration.json').read_bytes(),before)
            from scripts.integration import validate_bundle
            validate_bundle(root/'public/data')
            # Ignored, stale local candidates must not roll back a publication
            # received from Git (for example after an automated data refresh).
            candidates = root/'data/snapshots'
            candidates.mkdir(parents=True)
            (candidates/'campus-schedule.json').write_text('stale invalid candidate')
            again = subprocess.run([sys.executable,'-m','scripts.update_data','--reuse-current','--term',term],cwd=root,env=environment,text=True,capture_output=True)
            self.assertEqual(again.returncode,0,again.stderr)
            self.assertEqual((root/'public/data/integration.json').read_bytes(),before)


if __name__ == '__main__': unittest.main()
