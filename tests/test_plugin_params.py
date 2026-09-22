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
HELPER = re.compile(r'define(?:Info|Slider|Choice|Toggle)\([^;]*?"([A-Za-z0-9_]+)",\s*"', re.S)
DETAIL = re.compile(r'\{\s*"[a-z_]+",\s*"(info[A-Za-z0-9_]+)",\s*"')   # kDetails rows only
ROW = re.compile(r'\{\s*"(\w+)",')                                      # a row of a named table


def table(src, name, end):
    """The rows of one named table, so a regex cannot wander into option arrays."""
    return ROW.findall(src[src.index(name):src.index(end)])
FETCH = re.compile(r'fetch(?:String|Double|Choice|Int|Boolean|PushButton)Param\("([^"]+)"\)')


class PluginParams(unittest.TestCase):
    def setUp(self):
        with open(SRC, encoding='utf-8') as fh:
            self.src = fh.read()
        self.defined = (DEFINE.findall(self.src) + HELPER.findall(self.src)
                        + DETAIL.findall(self.src)
                        + table(self.src, 'toneNames[][3]', 'for (const auto& t : toneNames)'))

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
        and one clip attempted once.

        The wait escalates rather than being a single number. The point is the FIRST
        attempt: it is what a clip that reads normally costs, and it has to be short
        enough that the panel does not stall. The later, longer attempts only happen
        after a timeout, which means a long take on a slow drive - the case that used
        to come back with no metadata at all. The declared cost of that: a file that
        times out three times holds the panel for the sum of the budgets, which is
        why the total is capped here too.
        """
        self.assertIn('SF_DATALESS', self.src)
        self.assertIn('alreadyTried', self.src)
        budgets = re.search(r'kReadBudgetSec\[\] = \{([^}]*)\}', self.src)
        self.assertIsNotNone(budgets, 'budget del processo di lettura non trovato')
        secs = [int(v) for v in budgets.group(1).replace(',', ' ').split()]
        self.assertTrue(secs, 'nessun budget dichiarato')
        self.assertLessEqual(secs[0], 3, 'il primo tentativo blocca il pannello troppo a lungo')
        self.assertEqual(secs, sorted(secs), 'i budget devono crescere, non calare')
        self.assertLessEqual(sum(secs), 30, 'attesa complessiva troppo lunga')
        self.assertIn('kReadBudgetSec[attempt] * 20', self.src)   # 50 ms per tick

    def test_settings_version_is_saved(self):
        """Saved with every node, so a future release can recognise and convert old settings."""
        self.assertIn('defineIntParam("settingsVersion")', self.src)
        self.assertIn('fetchIntParam("settingsVersion")', self.src)
        self.assertIn('migrateSettings()', self.src)

    def test_data_level_sits_in_the_advanced_group(self):
        """defineChoice does not set a parent: without the explicit setParent the control
        would land at the top of the panel instead of under Avanzate."""
        self.assertRegex(self.src, r'defineChoice\([^;]*"dataLevel"[^;]*?\)\)\s*\{\s*\w+->setParent')
        self.assertIn('fetchChoiceParam("dataLevel")', self.src)
        self.assertIn('defineInfo(p_Desc, page, adv, "levelInfo"', self.src)

    def test_an_old_grade_keeps_the_data_level_correction_off(self):
        """A node saved before the correction existed must still open looking the same:
        the migration turns the stage off for it, and only new nodes get Automatico."""
        version = int(re.search(r'kSettingsVersion = (\d+)', self.src).group(1))
        self.assertGreaterEqual(version, 2, 'la migrazione ha bisogno di una versione nuova')
        self.assertIn('m_DataLevel->setValue(3)', self.src)

    def test_the_data_level_stage_is_reflected_in_isIdentity(self):
        """A node that only corrects the data level must not be skipped as neutral."""
        body = self.src[self.src.index('bool SLogMetaRaw::isIdentity'):]
        body = body[:body.index('\n}')]
        self.assertIn('p.levelFix == 0', body)

    def test_the_tone_trims_use_resolves_own_scale(self):
        """Resolve's numeric fields for this kind of trim - Col Boost, Shad, High,
        Mid/Detail - run -100..+100 with two decimals. DevelopParams keeps -1..1."""
        self.assertIn('0, -100, 100, -100, 100, 0.1', self.src)
        self.assertIn('setDigits(2)', self.src)

    def test_every_tone_trim_is_scaled_back_for_the_maths(self):
        """A trim added to the panel without dividing would arrive a hundred times
        too strong, which is not something the eye would forgive."""
        declared = table(self.src, 'toneNames[][3]', 'for (const auto& t : toneNames)')
        divided = re.findall(r'p\.\w+ = \(float\)\(m_\w+->getValueAtTime\(p_Time\) / kToneScale\)', self.src)
        self.assertEqual(len(declared), 6, 'i controlli di tono sono cambiati: %s' % declared)
        self.assertEqual(len(divided), len(declared), 'un controllo di tono non viene riscalato')

    def test_an_old_grade_keeps_its_tone_trims(self):
        """The saved numbers now mean a hundred times less, so they must be scaled."""
        version = int(re.search(r'kSettingsVersion = (\d+)', self.src).group(1))
        self.assertGreaterEqual(version, 3, 'la migrazione ha bisogno di una versione nuova')
        self.assertIn('p->setValue(p->getValue() * kToneScale)', self.src)

    def test_detail_fields_match_the_cache_record(self):
        """The shooting-data fields read keys of the JSON record: a rename must not blank them."""
        with open(os.path.join(ROOT, 'slogmetaraw', 'plugin_cache.py'), encoding='utf-8') as fh:
            cache_src = fh.read()
        record = cache_src[cache_src.index('return {'):]
        keys = set(re.findall(r"^\s*'([a-z_]+)':", record, re.M))
        used = set(re.findall(r'\{\s*"([a-z_]+)",\s*"info[A-Za-z0-9_]+",\s*"', self.src))
        used.add('camera_name')                       # the field at the top of the panel
        self.assertTrue(used, 'tabella kDetails non trovata')
        self.assertEqual(sorted(used - keys), [], 'campi del plugin assenti dal record JSON')


if __name__ == '__main__':
    unittest.main()
