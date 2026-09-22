# SPDX-License-Identifier: GPL-3.0-or-later
"""The as-shot white balance, and why an FX6 clip came out green.

The bug, in full. Sony stores the tint correction in acquisition metadata tag
0x811F in HUNDREDTHS of a tint unit: the clip FX6_0024.MXF reads 15.17 in Catalyst
Browse and in Resolve's own Camera Raw panel, and carries 1517 in the file. The
decoder handed that integer straight to a white balance model whose unit is
Duv * 3000, which put the as-shot white at Duv 0.506 - far outside the spectral
locus, Z negative - and the von Kries ratios came out NEGATIVE: R -0.95, G +1.17,
B -1.73. A picture with only its green channel left.

Two things then made it uncorrectable rather than merely wrong:

  * the Tint slider runs -100..+100, so it could not reach 1517 to cancel it. It
    sat pinned at 100 while the hidden as-shot value stayed at 1517, and moving it
    to 0 changed almost nothing because the shot side dominated by fifteen to one.
  * every control at rest still looked right, because the decode and the encode are
    exact inverses: with the chosen white equal to the shot white the ratios are 1
    and the whole error cancels. So "As shot" showed a correct picture and anything
    else did not - which is exactly what was reported.

These tests pin all of it: the scaling, the range checks, and the guarantee that no
number a file can carry produces a white the maths cannot represent.
"""
import math
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

from slogmetaraw import camera, rtmd  # noqa: E402
import develop_model as dm  # noqa: E402

SRC = os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'SLogMetaRaw.cpp')
HEADER = os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'DevelopMath.h.in')
SG3C = 8


def ratios(shot_k, shot_t, k, t):
    ws, wt = dm.white_lms(shot_k, shot_t), dm.white_lms(k, t)
    return [ws[i] / wt[i] for i in range(3)]


def gains(shot_k, shot_t, k, t):
    """What a neutral S-Gamut3.Cine pixel is multiplied by, per channel."""
    out = dm.develop([0.41, 0.41, 0.41], SG3C, 1, shot=(shot_k, shot_t, 800), temp=k, tint=t)
    return [c / 0.41 for c in out]


class SonyTintUnit(unittest.TestCase):
    def test_the_decoder_reports_the_number_the_camera_shows(self):
        """1517 in the file is 15.17 in Catalyst, in Resolve and here."""
        decode = rtmd.TAGS[0x811f][2]
        self.assertAlmostEqual(decode((1517).to_bytes(2, 'big')), 15.17, places=6)
        self.assertAlmostEqual(decode((0).to_bytes(2, 'big')), 0.0, places=9)
        self.assertAlmostEqual(decode((-800).to_bytes(2, 'big', signed=True)), -8.0, places=6)

    def test_an_empty_value_stays_empty(self):
        self.assertIsNone(rtmd.TAGS[0x811f][2](b''))


class ShotValuesAreRangeChecked(unittest.TestCase):
    def test_a_tint_the_slider_cannot_reach_is_clamped(self):
        """An as-shot value outside the slider's range is uncorrectable by
        definition: there is no setting that cancels it."""
        self.assertEqual(camera.shot_values({'white_balance_k': 5600, 'tint': 1517})[1], 100.0)
        self.assertEqual(camera.shot_values({'white_balance_k': 5600, 'tint': -1517})[1], -100.0)
        self.assertEqual(camera.shot_values({'white_balance_k': 5600, 'tint': 15.17})[1], 15.17)

    def test_a_kelvin_outside_the_planckian_range_is_not_used(self):
        for k in (0, -1, 900, 99999):
            got, _, _, estimated = camera.shot_values({'white_balance_k': k})
            self.assertTrue(camera.KELVIN_MIN <= got <= camera.KELVIN_MAX)
            self.assertTrue(estimated, 'un Kelvin fuori scala deve contare come stimato')

    def test_rubbish_never_reaches_the_maths(self):
        for bad in (float('nan'), float('inf'), 'x', None, [1]):
            k, tint, ei, _ = camera.shot_values({'white_balance_k': 5600, 'tint': bad, 'iso': bad})
            self.assertEqual(tint, tint)                     # not NaN
            self.assertTrue(-100.0 <= tint <= 100.0)
            self.assertEqual(ei, 800)

    def test_the_limit_is_the_one_the_header_enforces(self):
        with open(HEADER, encoding='utf-8') as fh:
            limit = float(re.search(r'#define SM_TINT_LIMIT ([\d.]+)', fh.read()).group(1))
        self.assertEqual(camera.TINT_LIMIT, limit)
        self.assertEqual(dm.TINT_LIMIT, limit)


class TheWhitePointIsAlwaysPhysical(unittest.TestCase):
    def test_no_tint_produces_a_negative_component(self):
        for tint in (-100000, -1517, -470, -100, 0, 15.17, 100, 470, 1517, 100000):
            for k in (1667, 2000, 3200, 5600, 8000, 25000):
                xyz = dm.white_xyz(k, tint)
                for c in xyz:
                    self.assertGreater(c, 0.0, 'bianco non fisico a %dK tint %s' % (k, tint))

    def test_no_pair_of_settings_produces_a_negative_gain(self):
        """A negative von Kries ratio is not a colour cast, it is a broken image."""
        for shot_t in (-1517, -100, 0, 15.17, 100, 1517):
            for chosen_t in (-100, 0, 100):
                for shot_k, k in ((3200, 5600), (5600, 3200), (5600, 5600), (2000, 25000)):
                    for r in ratios(shot_k, shot_t, k, chosen_t):
                        self.assertGreater(r, 0.0)

    def test_the_fx6_clip_no_longer_loses_two_channels(self):
        """The reported picture: R and B negative, G alone left standing."""
        raw = 1517
        # what shipped: the raw integer straight into the model, with no clamp and no
        # physical check. Recomputed here rather than called, because both guards are
        # now in white_xyz and the failure can no longer be reached through it.
        u0, v0 = dm.xy_uv(*dm.planck_xy(5600))
        u1, v1 = dm.xy_uv(*dm.planck_xy(5600 * 1.01))
        du, dv = u1 - u0, v1 - v0
        n = (-dv / math.hypot(du, dv), du / math.hypot(du, dv))
        if n[1] < 0:
            n = (-n[0], -n[1])
        x, y = dm.uv_xy(u0 + n[0] * raw / 3000, v0 + n[1] * raw / 3000)
        self.assertLess((1 - x - y) / y, 0.0, 'il bianco fuori scala aveva Z negativo')
        ws = dm.mul(dm.BR, [x / y, 1.0, (1 - x - y) / y])
        wt = dm.white_lms(5600, 0.0)
        before = dm.mul(dm.MATS[SG3C][1],
                        dm.mul(dm.BRI, [ws[i] / wt[i] * dm.mul(dm.BR, dm.mul(dm.MATS[SG3C][0], [1, 1, 1]))[i]
                                        for i in range(3)]))
        self.assertLess(min(before), 0.0, 'il caso che si voleva riprodurre non si riproduce')
        fixed_tint = camera.shot_values({'white_balance_k': 5600, 'tint': raw / 100.0})[1]
        after = gains(5600, fixed_tint, 5600, 0.0)
        self.assertGreater(min(after), 0.0)
        for g in after:                                     # and it is a trim, not a cast
            self.assertTrue(0.8 < g < 1.25, 'guadagno %.3f' % g)


class AsShotIsIdentity(unittest.TestCase):
    def test_choosing_the_shot_values_changes_nothing(self):
        for k, t in ((5600, 0.0), (3200, 15.17), (8000, -40.0), (2000, 100.0)):
            for g in gains(k, t, k, t):
                self.assertAlmostEqual(g, 1.0, delta=1e-6)

    def test_it_holds_even_for_a_value_that_had_to_be_clamped(self):
        """The clamp is applied to the shot reference, so the chosen side lands on
        the same number and the node stays neutral - a clamped clip is graded from a
        white that exists, not left uncorrectable."""
        t = camera.shot_values({'white_balance_k': 5600, 'tint': 1517})[1]
        for g in gains(5600, t, 5600, t):
            self.assertAlmostEqual(g, 1.0, delta=1e-6)


class ThePluginCannotDriftApartFromTheMetadata(unittest.TestCase):
    """Source-level guards. The drift that produced the report was structural: the
    sliders were seeded once, the hidden values were refreshed always, and nothing
    tied them together afterwards."""

    def setUp(self):
        with open(SRC, encoding='utf-8') as fh:
            self.src = fh.read()

    def test_as_shot_reads_the_shot_values_directly(self):
        """Not the sliders: the render must not depend on a setValue having happened
        at some point in the past."""
        self.assertIn('const bool asShot = (wbMode == 0);', self.src)
        self.assertIn('asShot ? m_ShotTemp->getValue()', self.src)
        self.assertIn('asShot ? m_ShotTint->getValue()', self.src)

    def test_a_failed_metadata_read_does_not_bind_the_clip(self):
        """Binding on failure is what stopped the sliders ever being seeded when the
        metadata finally turned up."""
        fail = self.src[self.src.index('if (!loadMeta('):self.src.index('setText(m_Camera, meta.fields')]
        self.assertNotIn('m_BoundPath->setValue', fail)

    def test_an_untouched_slider_follows_a_corrected_shot_value(self):
        self.assertIn('if (m_Temp->getValue() == oldK) m_Temp->setValue(meta.shotTemp);', self.src)
        self.assertIn('if (m_Tint->getValue() == oldT) m_Tint->setValue(meta.shotTint);', self.src)
        self.assertIn('if (m_EI->getValue() == oldEI) m_EI->setValue(meta.shotEI);', self.src)

    def test_the_record_is_range_checked_on_the_plugin_side_too(self):
        """The cache is a file on disk: it can be stale, hand edited, or written by a
        release whose scaling was wrong."""
        self.assertIn('m.shotTint >= -SM_TINT_LIMIT && m.shotTint <= SM_TINT_LIMIT', self.src)
        self.assertIn('m.shotTemp >= 1667.0 && m.shotTemp <= 25000.0', self.src)

    def test_a_clamped_tint_is_reported_to_the_colourist(self):
        self.assertIn('shotTintClamped', self.src)
        self.assertIn('fuori scala', self.src)

    def test_an_unknown_input_colourspace_is_not_assumed_in_silence(self):
        """A wrong guess is invisible until you touch something, because the decode
        and the encode are exact inverses."""
        self.assertIn('hostCsUnknown', self.src)
        self.assertIn('non riconosciuto', self.src)


class TheTankTopComesFromTheCameraCurve(unittest.TestCase):
    def test_the_plugin_uses_the_shared_definition(self):
        with open(SRC, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('p.eTop = sm_tank_top(camGammaCode >= 0 ? camGammaCode : nodeGamma);', src)

    def test_it_is_a_property_of_the_format_not_of_the_picture(self):
        self.assertAlmostEqual(dm.tank_top(9), math.log2(dm.decode1(1.0, 9) / 0.18), places=9)
        for g in (7, 8, 9):
            self.assertTrue(dm.TONE_E_TOP_MIN <= dm.tank_top(g) <= dm.TONE_E_TOP_MAX)


if __name__ == '__main__':
    unittest.main()
