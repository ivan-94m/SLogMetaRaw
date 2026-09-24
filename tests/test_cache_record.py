# SPDX-License-Identifier: GPL-3.0-or-later
"""Plugin cache records: partial sampling and which record may replace which."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

from slogmetaraw import read_clip, plugin_cache  # noqa: E402
import clip_fixtures as fx  # noqa: E402


class CacheRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.clip = os.path.join(cls.tmp, 'C0001.MP4')
        fx.build_mp4(cls.clip, frames=250)            # 11 samples make a complete reading
        cls.full = read_clip(cls.clip, max_samples=24)
        cls.part = read_clip(cls.clip, max_samples=8)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.cache = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.cache, True)
        patcher = mock.patch.object(plugin_cache, 'CACHE_DIR', self.cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self):
        with open(plugin_cache.cache_path(self.clip), encoding='utf-8') as fh:
            return json.load(fh)

    def test_partial_fields(self):
        """The record says how many samples were read and whether that is complete."""
        self.assertEqual(plugin_cache.VERSION, 6)
        plugin_cache.write_cache(self.part)
        rec = self.record()
        self.assertEqual((rec['samples_read'], rec['samples_planned'], rec['partial']), (8, 8, 1))
        plugin_cache.write_cache(self.full)
        self.assertEqual((self.record()['samples_read'], self.record()['partial']), (11, 0))

    def test_partial_never_replaces_complete(self):
        """A complete record survives a later partial one for the same file."""
        plugin_cache.write_cache(self.full)
        plugin_cache.write_cache(self.part)
        self.assertEqual(self.record()['partial'], 0)

    def test_cache_mode_keeps_a_complete_record(self):
        """--cache (keep_complete) never rewrites a complete record, even with a complete one."""
        plugin_cache.write_cache(self.full)
        with mock.patch.object(plugin_cache.os, 'replace', side_effect=AssertionError('riscritto')):
            path = plugin_cache.write_cache(self.full, keep_complete=True)
        self.assertEqual(path, plugin_cache.cache_path(self.clip))

    def test_a_changed_file_is_written_again(self):
        """A complete record of an older version of the file does not block a partial one."""
        plugin_cache.write_cache(self.full)
        rec = self.record()
        rec['file_mtime_ns'] += 1
        with open(plugin_cache.cache_path(self.clip), 'w', encoding='utf-8') as fh:
            json.dump(rec, fh)
        plugin_cache.write_cache(self.part, keep_complete=True)
        self.assertEqual(self.record()['partial'], 1)

    def test_an_old_unsupported_mxf_record_is_read_again(self):
        """A version 4 record with supported=0 (long FX6 MXF) is replaced by --cache."""
        mxf = os.path.join(self.tmp, 'A001C001.MXF')
        fx.build_mxf(mxf, frames=20, picture=20 * 1024)
        path = plugin_cache.cache_path(mxf)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'version': 4, 'path': plugin_cache.canonical_path(mxf), 'supported': 0,
                       'file_size': os.path.getsize(mxf),
                       'file_mtime_ns': os.stat(mxf).st_mtime_ns}, fh)
        plugin_cache.write_cache(read_clip(mxf, max_samples=8), keep_complete=True)
        with open(path, encoding='utf-8') as fh:
            rec = json.load(fh)
        self.assertEqual((rec['version'], rec['supported'], rec['cam_space'], rec['cam_gamma']), (6, 1, 8, 9))

    def test_resolve_status_sits_next_to_the_record(self):
        """<fnv>.resolve.json shares the record's name, so the plugin finds both from one hash."""
        self.assertEqual(plugin_cache.resolve_status_path(self.clip),
                         plugin_cache.cache_path(self.clip)[:-len('.json')] + '.resolve.json')

    def test_unverified_variation_is_said(self):
        """A partial reading without variations says so instead of implying none."""
        r = dict(self.part, changes={})
        self.assertIn('varia: non verificato', plugin_cache.build_record(r)['fps'])
        self.assertNotIn('varia', plugin_cache.build_record(dict(self.full, changes={}))['fps'])


if __name__ == '__main__':
    unittest.main()
