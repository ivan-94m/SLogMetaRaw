# SPDX-License-Identifier: GPL-3.0-or-later
"""The --to-resolve mode feeds the OpenFX plugin's "Rileggi metadata" button."""
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slogmetaraw.__main__ import to_resolve

RESULT = {'meta': {}, 'display': {}, 'sections': [], 'warnings': [], 'path': '/fake/clip.MP4'}


class ToResolveCli(unittest.TestCase):
    def run_cli(self, path):
        proc = subprocess.run([sys.executable, '-m', 'slogmetaraw', '--to-resolve', path],
                              capture_output=True, text=True, cwd=ROOT, timeout=60)
        return proc

    def test_missing_file_reports_json_error(self):
        proc = self.run_cli('/percorso/inesistente.MP4')
        self.assertEqual(proc.returncode, 1)
        out = json.loads(proc.stdout)
        self.assertFalse(out['ok'])
        self.assertIn('lettura metadata', out['error'])

    def test_missing_path_argument(self):
        proc = subprocess.run([sys.executable, '-m', 'slogmetaraw', '--to-resolve'],
                              capture_output=True, text=True, cwd=ROOT, timeout=60)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)['ok'])


class ToResolve(unittest.TestCase):
    def invoke(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = to_resolve(['/fake/clip.MP4'])
        return rc, json.loads(out.getvalue())

    def test_success_reports_counts(self):
        with mock.patch('slogmetaraw.__main__.read_clip', return_value=dict(RESULT)):
            with mock.patch('slogmetaraw.plugin_cache.write_cache'):
                with mock.patch('slogmetaraw.connect.connect', return_value=object()):
                    with mock.patch('slogmetaraw.connect.apply_path',
                                    return_value={'written': 34, 'failed': 1, 'clips': 1}):
                        rc, out = self.invoke()
        self.assertEqual(rc, 0)
        self.assertTrue(out['ok'])
        self.assertEqual(out['written'], 34)
        self.assertEqual(out['failed'], 1)
        self.assertEqual(out['clips'], 1)

    def test_resolve_failure_still_reports_read_ok(self):
        with mock.patch('slogmetaraw.__main__.read_clip', return_value=dict(RESULT)):
            with mock.patch('slogmetaraw.plugin_cache.write_cache'):
                with mock.patch('slogmetaraw.connect.connect',
                                side_effect=RuntimeError('clip non trovata nel Media Pool')):
                    rc, out = self.invoke()
        self.assertEqual(rc, 1)
        self.assertFalse(out['ok'])
        self.assertIn('Media Pool', out['error'])

    def test_cache_failure_is_reported_but_read_still_succeeds(self):
        with mock.patch('slogmetaraw.__main__.read_clip', return_value=dict(RESULT)):
            with mock.patch('slogmetaraw.plugin_cache.write_cache', side_effect=OSError('disco pieno')):
                with mock.patch('slogmetaraw.connect.connect', return_value=object()):
                    with mock.patch('slogmetaraw.connect.apply_path',
                                    return_value={'written': 34, 'failed': 0, 'clips': 1}):
                        rc, out = self.invoke()
        self.assertEqual(rc, 0)
        self.assertTrue(out['ok'])
        self.assertIn('disco pieno', out['cache'])

    def test_test_env_guard_skips_resolve(self):
        with mock.patch('slogmetaraw.__main__.read_clip', return_value=dict(RESULT)):
            with mock.patch('slogmetaraw.plugin_cache.write_cache'):
                with mock.patch('slogmetaraw.connect.connect') as connect:
                    with mock.patch.dict(os.environ, {'SLOGMETARAW_TEST_NO_RESOLVE': '1'}):
                        rc, out = self.invoke()
        self.assertEqual(rc, 1)
        self.assertFalse(out['ok'])
        self.assertIn('test', out['error'])
        connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
