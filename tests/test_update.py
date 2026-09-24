# SPDX-License-Identifier: GPL-3.0-or-later
"""Update check logic: version comparison, the state cache and the plugin's CLI (no network)."""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slogmetaraw import update, __main__ as cli  # noqa: E402

DMG = 'https://github.com/ivan-94m/SLogMetaRaw/releases/download/v9.9.9/SLogMetaRaw-9.9.9.dmg'
DETAILS = {'notes': 'lunghe note\ncon a capo', 'title': 'S-Log MetaRaw  9.9.9\n', 'page': 'p',
           'dmg_url': DMG, 'dmg_name': 'SLogMetaRaw-9.9.9.dmg', 'size': 1234}
NO_NETWORK = AssertionError('rete non permessa')


class Versions(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(update.parse_version('v1.2.3'), (1, 2, 3))
        self.assertEqual(update.parse_version('1.0.0'), (1, 0, 0))
        self.assertIsNone(update.parse_version(''))
        self.assertIsNone(update.parse_version('v1.2'))
        self.assertIsNone(update.parse_version('latest'))

    def test_newer(self):
        self.assertTrue(update.is_newer('1.0.1', 'v1.1.0'))
        self.assertFalse(update.is_newer('1.1.0', 'v1.1.0'))
        self.assertFalse(update.is_newer('1.1.0', 'v1.0.1'))
        self.assertFalse(update.is_newer('0.9', 'v1.0'))   # not semver


class State(unittest.TestCase):
    def test_blank_shape(self):
        b = update.blank()
        for key in ('ok', 'current', 'latest', 'newer', 'tag', 'notes', 'title',
                    'page', 'dmg_url', 'dmg_name', 'size', 'checked_at', 'error'):
            self.assertIn(key, b)

    def test_cached_result_is_reused_without_network(self):
        fresh = update.blank()
        fresh['ok'] = True
        fresh['latest'] = '1.1.0'
        fresh['checked_at'] = time.time()
        with mock.patch.object(update, 'STATE_PATH', '/tmp/smr-update-test.json'):
            update.write_state(fresh)
            with mock.patch.object(update, 'latest_tag',
                                   side_effect=AssertionError('rete non permessa')):
                result = update.check()
            self.assertTrue(result['ok'])
            self.assertEqual(result['latest'], '1.1.0')
            os.unlink('/tmp/smr-update-test.json')

    def test_stale_cache_is_refreshed(self):
        stale = update.blank()
        stale['ok'] = True
        stale['checked_at'] = time.time() - 10 * update.CACHE_TTL
        with mock.patch.object(update, 'STATE_PATH', '/tmp/smr-update-test2.json'):
            update.write_state(stale)
            with mock.patch.object(update, 'latest_tag', return_value='v9.9.9'):
                with mock.patch.object(update, 'release_details', return_value={}):
                    result = update.check()
            self.assertEqual(result['tag'], 'v9.9.9')
            self.assertTrue(result['newer'])
            os.unlink('/tmp/smr-update-test2.json')


class PluginCli(unittest.TestCase):
    """--update-check: one flat JSON line for the plugin's version button."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        for name, value in (('SUPPORT_DIR', self.dir), ('STATE_PATH', os.path.join(self.dir, 'update.json'))):
            patcher = mock.patch.object(update, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def state(self, age_h, **values):
        st = update.blank('1.2.0')
        st.update(dict(dict(ok=True, latest='1.2.0', tag='v1.2.0', checked_at=time.time() - age_h * 3600), **values))
        update.write_state(st)

    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli.main(['--update-check'] + list(args))
        lines = out.getvalue().splitlines()
        self.assertEqual((rc, len(lines)), (0, 1))
        return json.loads(lines[0])

    def test_a_result_younger_than_a_day_is_reused(self):
        """23 h old: no network at all."""
        self.state(23)
        with mock.patch.object(update, 'latest_tag', side_effect=NO_NETWORK), \
                mock.patch.object(update, 'release_details', side_effect=NO_NETWORK):
            out = self.run_cli('--current', '1.2.0')
        self.assertEqual((out['ok'], out['newer'], out['latest']), (1, 0, '1.2.0'))

    def test_a_result_older_than_a_day_asks_github(self):
        """25 h old: GitHub is asked, and a newer release comes with its installer."""
        self.state(25)
        with mock.patch.object(update, 'latest_tag', return_value='v9.9.9') as tag, \
                mock.patch.object(update, 'release_details', return_value=dict(DETAILS)):
            out = self.run_cli('--current', '1.2.0')
        tag.assert_called_once()
        self.assertEqual((out['ok'], out['newer'], out['latest'], out['dmg_url']), (1, 1, '9.9.9', DMG))

    def test_force_asks_github_even_when_fresh(self):
        """A click (--force) skips the day-long reuse."""
        self.state(23)
        with mock.patch.object(update, 'latest_tag', return_value='v1.2.0') as tag:
            out = self.run_cli('--current', '1.2.0', '--force')
        tag.assert_called_once()
        self.assertEqual(out['newer'], 0)

    def test_offline_is_an_answer_not_a_failure(self):
        """No network: error set, exit code 0."""
        with mock.patch.object(update, 'latest_tag', side_effect=urllib.error.URLError('offline')):
            out = self.run_cli('--current', '1.2.0')
        self.assertEqual((out['ok'], out['newer']), (0, 0))
        self.assertIn('connessione', out['error'])

    def test_script_state_for_another_version_is_recomputed(self):
        """update.json written by the script for 1.1.0 (newer, no installer yet) serves 1.2.0 too."""
        self.state(1, latest='1.3.0', tag='v1.3.0', newer=False, current='1.1.0')
        with mock.patch.object(update, 'latest_tag', side_effect=NO_NETWORK), \
                mock.patch.object(update, 'release_details', return_value=dict(DETAILS)) as details:
            out = self.run_cli('--current', '1.2.0')
        details.assert_called_once()
        self.assertEqual((out['newer'], out['current'], out['latest']), (1, '1.2.0', '1.3.0'))

    def test_one_flat_line_without_notes(self):
        """Only strings and 0/1 integers, no release notes, the title on one line."""
        self.state(25)
        with mock.patch.object(update, 'latest_tag', return_value='v9.9.9'), \
                mock.patch.object(update, 'release_details', return_value=dict(DETAILS)):
            out = self.run_cli()
        self.assertNotIn('notes', out)
        self.assertEqual(out['current'], cli_version())
        self.assertEqual(out['title'], 'S-Log MetaRaw 9.9.9')
        for key, value in out.items():
            self.assertIsInstance(value, (str, int), key)
            self.assertNotIsInstance(value, bool, key)
        self.assertEqual(set(out), {'ok', 'newer', 'current', 'lib_version', 'latest', 'tag', 'title',
                                    'dmg_url', 'dmg_name', 'size', 'error'})


def cli_version():
    from slogmetaraw import __version__
    return __version__


if __name__ == '__main__':
    unittest.main()
