# SPDX-License-Identifier: GPL-3.0-or-later
"""The --to-resolve mode feeds the OpenFX plugin's "Rileggi metadata" button."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

from slogmetaraw import __main__ as cli, plugin_cache  # noqa: E402
import clip_fixtures as fx  # noqa: E402

RESULT = {'meta': {}, 'display': {}, 'sections': [], 'warnings': [], 'path': '/fake/clip.MP4'}
REPORT = {'written': 34, 'failed': 1, 'clips': 1, 'data_level': {'host': 'Full'}}

# A child like the plugin's, with a fake Resolve: argv = root, connection mode, clip, marker file.
CHILD = r'''
import sys, threading, time
sys.path.insert(0, sys.argv[1])
from slogmetaraw import __main__ as cli, connect
mode, clip, marker = sys.argv[2:5]

def fake_connect():
    open(marker, 'w').close()
    if mode == 'blocked':
        threading.Event().wait()
    time.sleep(float(mode))
    return object()

connect.connect = fake_connect
connect.apply_path = lambda resolve, path, r: {'written': 34, 'failed': 0, 'clips': 1,
                                               'data_level': {'host': 'Full'}}
sys.exit(cli.main(['--to-resolve', clip]))
'''


class Detached(unittest.TestCase):
    """The first line comes at once; the write into Resolve lands in <fnv>.resolve.json."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        cls.clip = os.path.join(cls.home, 'C0001.MP4')
        fx.build_mp4(cls.clip, frames=250)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def start(self, mode, **env):
        self.marker = os.path.join(self.home, 'connected-%s' % mode)
        extra, env = env, dict(os.environ, HOME=self.home)
        env.pop('SLOGMETARAW_TEST_NO_RESOLVE', None)
        env.update(extra)
        self.began = time.monotonic()
        proc = subprocess.Popen([sys.executable, '-c', CHILD, ROOT, mode, self.clip, self.marker],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        first = proc.stdout.readline()
        self.first_after = time.monotonic() - self.began
        out, err = proc.communicate(timeout=5)   # EOF: the detached writer does not hold the pipe
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(out, '')
        return json.loads(first)

    def status_path(self):
        cache = os.path.join(self.home, 'Library/Application Support/SLogMetaRaw/cache')
        with mock.patch.object(plugin_cache, 'CACHE_DIR', cache):
            return plugin_cache.resolve_status_path(self.clip)

    def wait_status(self, limit):
        path = self.status_path()
        while time.monotonic() - self.began < limit:
            if os.path.exists(path):
                with open(path, encoding='utf-8') as fh:
                    return json.load(fh)
            time.sleep(0.02)
        self.fail('nessun esito entro %.1f s' % limit)

    def test_first_line_is_immediate_with_a_slow_resolve(self):
        """Resolve answering in 1 s: {"cache": 1} within 0.5 s, the outcome right after."""
        self.assertEqual(self.start('1.0'), {'cache': 1})
        self.assertLess(self.first_after, 0.5)
        status = self.wait_status(3.0)
        self.assertEqual((status['ok'], status['written'], status['level_host'], status['error']),
                         (1, 34, 'Full', ''))

    def test_a_blocked_connection_ends_in_an_error_within_3_5_s(self):
        """Resolve never answering: the error JSON is written by the time limit."""
        self.assertEqual(self.start('blocked'), {'cache': 1})
        self.assertLess(self.first_after, 0.5)
        status = self.wait_status(3.5)
        self.assertEqual(status['ok'], 0)
        self.assertIn('non risponde', status['error'])

    def test_test_environment_never_connects(self):
        """SLOGMETARAW_TEST_NO_RESOLVE: the cache is written, Resolve is never contacted."""
        self.assertEqual(self.start('0', SLOGMETARAW_TEST_NO_RESOLVE='1'), {'cache': 1})
        status = self.wait_status(2.0)
        self.assertEqual(status['ok'], 0)
        self.assertIn('test', status['error'])
        self.assertFalse(os.path.exists(self.marker))


class ToResolveCli(unittest.TestCase):
    def run_cli(self, *args):
        with tempfile.TemporaryDirectory() as home:
            return subprocess.run([sys.executable, '-m', 'slogmetaraw', '--to-resolve'] + list(args),
                                  capture_output=True, text=True, cwd=ROOT, timeout=60,
                                  env=dict(os.environ, HOME=home))

    def test_missing_file_reports_json_error(self):
        """An unreadable clip gives {"cache": 0, "error": ...} and exit 1."""
        proc = self.run_cli('/percorso/inesistente.MP4')
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(proc.stdout.splitlines()), 1)
        out = json.loads(proc.stdout)
        self.assertEqual(out['cache'], 0)
        self.assertIn('lettura metadata', out['error'])

    def test_missing_path_argument(self):
        """No clip at all is an error too."""
        proc = self.run_cli()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)['cache'], 0)


class InProcess(unittest.TestCase):
    def setUp(self):
        self.cache = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.cache, True)
        patcher = mock.patch.object(plugin_cache, 'CACHE_DIR', self.cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    def invoke(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli.to_resolve(['/fake/clip.MP4'], detach=False)
        with open(plugin_cache.resolve_status_path('/fake/clip.MP4'), encoding='utf-8') as fh:
            status = json.load(fh)
        return rc, [json.loads(line) for line in out.getvalue().splitlines()], status

    def test_success_reports_counts(self):
        """The outcome file carries written, failed and Resolve's data level, all flat."""
        with mock.patch('slogmetaraw.__main__.read_clip', return_value=dict(RESULT)), \
                mock.patch('slogmetaraw.plugin_cache.write_cache'), \
                mock.patch('slogmetaraw.connect.connect', return_value=object()), \
                mock.patch('slogmetaraw.connect.apply_path', return_value=REPORT):
            rc, lines, status = self.invoke()
        self.assertEqual((rc, lines), (0, [{'cache': 1}]))
        self.assertEqual(status, {'ok': 1, 'written': 34, 'failed': 1, 'clips': 1,
                                  'level_host': 'Full', 'error': ''})

    def test_resolve_failure_is_in_the_outcome(self):
        """A clip missing from the Media Pool: the cache line is still 1."""
        with mock.patch('slogmetaraw.__main__.read_clip', return_value=dict(RESULT)), \
                mock.patch('slogmetaraw.plugin_cache.write_cache'), \
                mock.patch('slogmetaraw.connect.connect',
                           side_effect=RuntimeError('clip non trovata nel Media Pool')):
            rc, lines, status = self.invoke()
        self.assertEqual((rc, lines), (0, [{'cache': 1}]))
        self.assertEqual(status['ok'], 0)
        self.assertIn('Media Pool', status['error'])

    def test_cache_failure_is_reported_but_resolve_is_still_written(self):
        """A full disk is reported in the first line; the Media Pool write still runs."""
        with mock.patch('slogmetaraw.__main__.read_clip', return_value=dict(RESULT)), \
                mock.patch('slogmetaraw.plugin_cache.write_cache', side_effect=OSError('disco pieno')), \
                mock.patch('slogmetaraw.connect.connect', return_value=object()), \
                mock.patch('slogmetaraw.connect.apply_path', return_value=REPORT):
            rc, lines, status = self.invoke()
        self.assertEqual(rc, 0)
        self.assertEqual(lines[0]['cache'], 0)
        self.assertIn('disco pieno', lines[0]['error'])
        self.assertEqual(status['ok'], 1)

    def test_an_earlier_outcome_is_removed_first(self):
        """A press whose read fails leaves no outcome of a previous press behind."""
        path = plugin_cache.resolve_status_path('/fake/clip.MP4')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'ok': 1}, fh)
        out = io.StringIO()
        with redirect_stdout(out), mock.patch('slogmetaraw.__main__.read_clip', side_effect=OSError('sparita')):
            self.assertEqual(cli.to_resolve(['/fake/clip.MP4'], detach=False), 1)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(json.loads(out.getvalue())['cache'], 0)


if __name__ == '__main__':
    unittest.main()
