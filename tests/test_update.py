# SPDX-License-Identifier: GPL-3.0-or-later
"""Update check logic: version comparison and the state cache (no network)."""
import os
import sys
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slogmetaraw import update  # noqa: E402


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


if __name__ == '__main__':
    unittest.main()
