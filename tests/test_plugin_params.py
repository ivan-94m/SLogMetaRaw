# SPDX-License-Identifier: GPL-3.0-or-later
"""Guards on the OpenFX parameters: duplicate names crash DaVinci Resolve.

A duplicate name (two params called "exposure") segfaults Resolve inside
describeInContext, and a fetch of a name that was never defined throws on load.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'SLogMetaRaw.cpp')

DEFINE = re.compile(r'define(?:String|Double|Choice|Int|Boolean|PushButton|Group)Param\("([^"]+)"\)')
HELPER = re.compile(r'define(?:Info|Slider|Choice)\([^;]*?"([A-Za-z0-9_]+)",\s*"', re.S)
DETAIL = re.compile(r'\{\s*"[a-z_]+",\s*"([A-Za-z0-9_]+)",\s*"')
PAIR = re.compile(r'\{\s*"([A-Za-z0-9_]+)",\s*"[^"]+"\s*\}')      # { "shadows", "Shadows" }
FETCH = re.compile(r'fetch(?:String|Double|Choice|Int|Boolean|PushButton)Param\("([^"]+)"\)')


class PluginParams(unittest.TestCase):
    def setUp(self):
        with open(SRC, encoding='utf-8') as fh:
            self.src = fh.read()
        self.defined = (DEFINE.findall(self.src) + HELPER.findall(self.src)
                        + DETAIL.findall(self.src) + PAIR.findall(self.src))

    def test_names_are_unique(self):
        seen, dupes = set(), []
        for name in self.defined:
            (dupes.append(name) if name in seen else seen.add(name))
        self.assertEqual(dupes, [], 'parametri con nome duplicato: %s' % dupes)

    def test_every_fetched_param_exists(self):
        missing = sorted(set(FETCH.findall(self.src)) - set(self.defined))
        self.assertEqual(missing, [], 'parametri letti ma mai definiti: %s' % missing)

    def test_settings_version_is_saved(self):
        """Saved with every node, so a future release can recognise and convert old settings."""
        self.assertIn('defineIntParam("settingsVersion")', self.src)
        self.assertIn('fetchIntParam("settingsVersion")', self.src)
        self.assertIn('migrateSettings()', self.src)

    def test_detail_fields_match_the_cache_record(self):
        """The shooting-data fields read keys of the JSON record: a rename must not blank them."""
        with open(os.path.join(ROOT, 'slogmetaraw', 'plugin_cache.py'), encoding='utf-8') as fh:
            cache_src = fh.read()
        record = cache_src[cache_src.index('return {'):]
        keys = set(re.findall(r"^\s*'([a-z_]+)':", record, re.M))
        used = set(re.findall(r'\{\s*"([a-z_]+)",\s*"[A-Za-z0-9_]+",\s*"', self.src))
        used.add('camera_name')                       # the field at the top of the panel
        self.assertTrue(used, 'tabella kDetails non trovata')
        self.assertEqual(sorted(used - keys), [], 'campi del plugin assenti dal record JSON')


if __name__ == '__main__':
    unittest.main()
