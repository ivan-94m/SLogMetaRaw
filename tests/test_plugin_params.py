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

    def test_names_are_claimed_per_context(self):
        """describeInContext runs once per context: a set shared between calls would
        leave the second context with no parameters, and the instance then fails to build."""
        self.assertNotIn('static std::set<std::string> used;', self.src,
                         'il set dei nomi non deve sopravvivere tra una chiamata e l\'altra')
        body = self.src[self.src.index('void SLogMetaRawFactory::describeInContext'):]
        self.assertIn('usedNames().clear()', body[:600],
                      'describeInContext deve azzerare i nomi già usati')

    def test_instance_degrades_instead_of_crashing(self):
        """A missing parameter must disable the node, never throw back into the host."""
        ctor = self.src[self.src.index('SLogMetaRaw::SLogMetaRaw(OfxImageEffectHandle'):]
        ctor = ctor[:ctor.index('\n}\n')]
        self.assertIn('try {', ctor)
        self.assertIn('catch (...)', ctor)
        self.assertIn('m_Ready = true;', ctor)
        for entry in ('bool SLogMetaRaw::isIdentity', 'void SLogMetaRaw::render',
                      'void SLogMetaRaw::beginEdit', 'void SLogMetaRaw::changedParam',
                      'void SLogMetaRaw::changedClip', 'bool SLogMetaRaw::buildParams'):
            body = self.src[self.src.index(entry):]
            self.assertIn('m_Ready', body[:body.index('\n}\n')], '%s non controlla m_Ready' % entry)

    def test_reader_cannot_freeze_the_ui(self):
        """The metadata reader runs on the UI thread: bounded wait, no cloud downloads,
        and one attempt per clip."""
        self.assertIn('SF_DATALESS', self.src)
        self.assertIn('alreadyTried', self.src)
        wait = re.search(r'for \(int waited = 0; waited < (\d+); \+\+waited\)', self.src)
        self.assertIsNotNone(wait, 'watchdog del processo di lettura non trovato')
        self.assertLessEqual(int(wait.group(1)) * 0.05, 10, 'attesa massima troppo lunga')

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
