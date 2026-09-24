# SPDX-License-Identifier: GPL-3.0-or-later
"""Guards on the OpenFX parameters: duplicate names crash DaVinci Resolve.

A duplicate name (two params called "exposure") segfaults Resolve inside
describeInContext, and a fetch of a name that was never defined throws on load.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from plugin_build import body, source  # noqa: E402

DEFINE = re.compile(r'define(?:String|Double|Choice|Int|Boolean|PushButton|Group)Param\("([^"]+)"\)')
HELPER = re.compile(r'define(?:Info|Slider|Choice|Toggle|Check|Button|Group|HiddenDouble|HiddenInt)\(\s*d,\s*page,\s*'
                    r'(?:\w+,\s*)?"([A-Za-z0-9_]+)"')
DETAIL = re.compile(r'\{\s*"[a-z_]+",\s*"(info[A-Za-z0-9_]+)",\s*"')   # kDetails rows only
ROW = re.compile(r'\{\s*"(\w+)",')                                      # a row of a named table


def zone_names():
    """The zone controls are named at runtime: <prefix><Zone><Field> (src/common/ZoneParams.cpp)."""
    names = []
    for prefix, fields in (('zone', ('Exp', 'Sat', 'Range', 'Falloff')), ('localZone', ('Exp', 'Range', 'Falloff'))):
        names.append(prefix + 'Pivot')
        names += [prefix + z + f for z in ('Black', 'Shadow', 'Light', 'Specular') for f in fields]
    return names


def table(src, name, end):
    """The rows of one named table, so a regex cannot wander into option arrays."""
    return ROW.findall(src[src.index(name):src.index(end)])
TONES = re.compile(r'\{\s*"(tone\w+)",\s*"')                             # kToneSliders rows
LEGACY = re.compile(r'\{\s*"(\w+)",\s*"(?:H|S|C|Sat|Boost|Recovery)"\s*\}')
FETCH = re.compile(r'fetch(?:String|Double|Choice|Int|Boolean|PushButton)Param\("([^"]+)"\)')


class PluginParams(unittest.TestCase):
    def setUp(self):
        self.src = source()
        self.defined = (DEFINE.findall(self.src) + HELPER.findall(self.src) + DETAIL.findall(self.src)
                        + TONES.findall(self.src) + LEGACY.findall(self.src) + ['version'] + zone_names())

    def test_names_are_unique(self):
        """Per plugin: each factory's describeInContext is one namespace (the host test also checks
        the names built at runtime, such as the zone controls)."""
        for factory in re.findall(r'void (\w+Factory)::describeInContext', self.src):
            text = body(self.src, 'void %s::describeInContext' % factory)
            names = DEFINE.findall(text) + HELPER.findall(text)
            dupes = sorted({n for n in names if names.count(n) > 1})
            self.assertEqual(dupes, [], '%s: parametri con nome duplicato: %s' % (factory, dupes))

    def test_every_fetched_param_exists(self):
        missing = sorted(set(FETCH.findall(self.src)) - set(self.defined))
        self.assertEqual(missing, [], 'parametri letti ma mai definiti: %s' % missing)

    def test_names_are_claimed_per_context(self):
        """describeInContext runs once per context: a set shared between calls would
        leave the second context with no parameters, and the instance then fails to build."""
        self.assertNotIn('static std::set<std::string> used;', self.src,
                         'il set dei nomi non deve sopravvivere tra una chiamata e l\'altra')
        for factory in re.findall(r'void (\w+Factory)::describeInContext', self.src):
            text = body(self.src, 'void %s::describeInContext' % factory)
            self.assertIn('resetParamNames()', text[:300], '%s deve azzerare i nomi già usati' % factory)

    def test_instance_degrades_instead_of_crashing(self):
        """A missing parameter must disable the node, never throw back into the host."""
        ctor = body(self.src, 'DevelopEffect::DevelopEffect(OfxImageEffectHandle')
        self.assertIn('try {', ctor)
        self.assertIn('catch (...)', ctor)
        self.assertIn('m_Ready = true;', ctor)
        for entry in ('bool DevelopEffect::isIdentity', 'void DevelopEffect::render',
                      'void DevelopEffect::beginEdit', 'void DevelopEffect::changedParam',
                      'void DevelopEffect::changedClip', 'bool DevelopEffect::buildParams'):
            self.assertIn('m_Ready', body(self.src, entry), '%s non controlla m_Ready' % entry)

    def test_reader_cannot_freeze_the_ui(self):
        """The reader is waited for on the UI thread only briefly, then left to finish on its own:
        no blocking waitpid, no fixed sleeps, no cloud downloads, no retry storm, and no reader
        at all while a project opens."""
        self.assertIn('SF_DATALESS', self.src)
        sync = int(re.search(r'kSyncWaitMs = (\d+);', self.src).group(1))
        reload_ = int(re.search(r'kReloadWaitMs = (\d+);', self.src).group(1))
        self.assertLessEqual(sync, 500)
        self.assertLessEqual(reload_, 2000)
        self.assertIn('kRetryAfterMs', self.src)
        self.assertNotIn('waitpid(pid, nullptr, 0)', self.src)
        self.assertNotIn('usleep', self.src)
        self.assertIn('ECHILD', self.src)
        ctor = body(self.src, 'DevelopEffect::DevelopEffect(OfxImageEffectHandle')
        self.assertIn('MetaMode::CacheOnly', ctor)
        self.assertNotIn('MetaMode::Read', ctor)

    def test_settings_version_is_saved(self):
        """Saved with every node, so a future release can recognise and convert old settings."""
        self.assertIn('"settingsVersion"', self.src)
        self.assertIn('fetchIntParam("settingsVersion")', self.src)
        self.assertIn('migrateSettings()', self.src)
        self.assertEqual(int(re.search(r'kSettingsVersion = (\d+)', self.src).group(1)), 5)

    def test_data_level_sits_in_the_advanced_group(self):
        """defineChoice sets no parent by itself: without one the control would land at the top."""
        self.assertRegex(self.src, r'defineChoice\([^;]*"dataLevel"[^;]*,\s*adv\);')
        self.assertIn('fetchChoiceParam("dataLevel")', self.src)
        self.assertIn('defineInfo(d, page, adv, "levelInfo"', self.src)

    def test_a_1_0_grade_keeps_the_data_level_correction_off(self):
        """Only a node saved at settings v1 predates the correction: 0 is a new node."""
        self.assertIn('if (saved == 1) m_DataLevel->setValue(3);', self.src)
        self.assertNotIn('saved <= 1', self.src)

    def test_the_data_level_stage_is_reflected_in_isIdentity(self):
        """A node that only corrects the data level must not be skipped as neutral."""
        self.assertIn('p.levelFix == 0', body(self.src, 'bool DevelopEffect::isIdentity'))

    def test_the_tone_controls_use_resolves_own_scale(self):
        """Resolve's trims of this kind run -100..+100 with two decimals; the zones are in stops."""
        tone_table = body(self.src, 'void defineToneParams(')
        self.assertIn('0, -100, 100, -100, 100, 0.1, t.hint, tones', tone_table)
        self.assertIn('setDigits(2)', tone_table)
        self.assertEqual(len(TONES.findall(self.src)), 7)

    def test_every_tone_control_reaches_the_maths(self):
        """One table feeds define, read, enable and reset: a slider cannot be shown and ignored."""
        fields = re.findall(r'&SMToneControls::(\w+)', self.src)
        self.assertEqual(sorted(fields), sorted(['contrast', 'highlights', 'shadows', 'whites', 'blacks',
                                                  'vibrance', 'saturation']))
        self.assertIn('readToneControls(*this, p_Time)', body(self.src, 'bool DevelopEffect::buildParams'))
        self.assertIn('sm_set_tone(&p, &tones', body(self.src, 'bool DevelopEffect::buildParams'))

    def test_the_1_1_tones_are_kept_by_name_but_never_rendered(self):
        """No legacy engine: the old values only produce the note that they were dropped."""
        self.assertEqual(sorted(LEGACY.findall(self.src)),
                         sorted(['highlights', 'shadows', 'contrast', 'saturation', 'colorBoost', 'colorRecovery']))
        self.assertIn('setIsSecret(true)', body(self.src, 'void defineLegacyTones('))
        render_path = body(self.src, 'bool DevelopEffect::buildParams') + body(self.src, 'void DevelopEffect::render')
        for name in ('"highlights"', '"shadows"', '"colorRecovery"', '"colorBoost"'):
            self.assertNotIn(name, render_path)

    def test_the_zone_group_starts_closed(self):
        self.assertIn('defineGroup(d, page, "zonesGroup", "Zone", false)', self.src)

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
