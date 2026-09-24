# SPDX-License-Identifier: GPL-3.0-or-later
"""Highlights is a film shoulder: what it must do, and what it must never do.

2.0.0's Highlights was a zone exposure shift (slope 1 -> 0.35 -> 1): the top only moved down 2 stops, still above
display white, and what landed under it came out as flat grey plates. The shoulder's slope falls monotonically towards
the top, and at -100 the camera's recorded maximum lands exactly on Bianco (softClipLevel).
"""
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import develop_model as dm  # noqa: E402
from model import color as C  # noqa: E402
from model import tone as T  # noqa: E402

GRID = [-8.0 + 0.02 * i for i in range(901)]   # -8 .. +10 stops


def curve(controls, expo=1.0):
    return T.set_tone(controls, expo=expo)


def out(e, p):
    """T(e): the stop value a pixel at e (after Blacks) leaves the curve with."""
    return e + T.t5_curve(e, p)[0]


def slopes(p, grid=GRID):
    ts = [out(e, p) for e in grid]
    return [(b - a) / (y - x) for a, b, x, y in zip(ts, ts[1:], grid, grid[1:])]


class Shoulder(unittest.TestCase):
    def test_at_zero_it_is_not_there(self):
        self.assertEqual(curve({})['hlE'], 0.0)
        self.assertEqual(curve({'toneHighlights': 0})['hlE'], 0.0)

    def test_grey_and_everything_below_do_not_move(self):
        for v in (-100, -50, -10, 10, 100):
            p = curve({'toneHighlights': v})
            for e in (-8.0, -3.0, -1.0, 0.0):
                self.assertEqual(T.t5_curve(e, p)[0], 0.0, 'Highlights %d at %+g stops' % (v, e))

    def test_skin_a_stop_over_grey_barely_moves(self):
        for v in (-10, -50, -100):
            self.assertLess(abs(out(1.0, curve({'toneHighlights': v})) - 1.0), 0.06, v)

    def test_the_slope_falls_monotonically_and_never_below_the_floor(self):
        s = slopes(curve({'toneHighlights': -100}))
        self.assertGreater(min(s), T.SM_T5_HL_SMIN - 1e-3)
        self.assertLessEqual(max(s), 1.0 + 1e-9)
        above = [x for e, x in zip(GRID, s) if e >= 0.0]
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(above, above[1:])), 'the slope must never climb back')

    def test_positive_is_a_bounded_expansion(self):
        s = slopes(curve({'toneHighlights': 100}))
        self.assertGreaterEqual(min(s), 1.0 - 1e-9)
        self.assertLessEqual(max(s), 1.0 + T.SM_T5_HL_CPLUS + 1e-9)

    def test_no_combination_solarises(self):
        rnd = random.Random(5)
        for _ in range(60):
            panel = {'toneHighlights': rnd.uniform(-100, 100), 'toneContrast': rnd.uniform(-100, 100),
                     'toneWhites': rnd.uniform(-100, 100), 'toneShadows': rnd.uniform(-100, 100),
                     'softClipLevel': rnd.uniform(1.5, 6), 'softClip': rnd.random() < 0.5}
            self.assertGreater(min(slopes(curve(panel))), -1e-9, panel)   # flat under the roof, never falling

    def test_a_stronger_setting_never_brings_a_tone_back(self):
        prev = None
        for v in range(0, -101, -5):
            ts = [out(e, curve({'toneHighlights': v})) for e in GRID]
            if prev is not None:
                self.assertTrue(all(b <= a + 1e-9 for a, b in zip(prev, ts)), v)
            prev = ts

    def test_minus_100_lands_the_recorded_top_on_bianco(self):
        """...or at least 1.5 stops under where Contrast puts the top, when Bianco is higher than that."""
        for white in (2.5, 3.5, 4.5):
            for con in (-50, -20, 0):
                p = curve({'toneHighlights': -100, 'softClipLevel': white, 'toneContrast': con})
                top = T.contrast_map(T.SM_T5_HL_TOP, 2.0 ** (con / 100.0) - 1.0, 0.0)
                want = min(white, top - T.SM_T5_HL_MINPULL)
                self.assertAlmostEqual(out(T.SM_T5_HL_TOP, p), want, places=6, msg='Bianco %g Contrast %d' % (white, con))
            # positive Contrast steepens the top: the slope floor lets it land a few hundredths of a stop over
            p = curve({'toneHighlights': -100, 'softClipLevel': white, 'toneContrast': 30})
            self.assertAlmostEqual(out(T.SM_T5_HL_TOP, p), white, delta=0.05)

    def test_a_landing_out_of_reach_stops_at_the_slope_floor(self):
        """Bianco too low for the range to fit (or EI doubled): the slope stays 0.06, the top stays just above."""
        for controls, expo, top in (({'softClipLevel': 2.0, 'toneContrast': -50}, 1.0, 6.0), ({}, 2.0, 7.0),
                                    ({'toneContrast': 50}, 1.0, 6.0)):
            p = curve(dict(controls, toneHighlights=-100), expo=expo)
            white = controls.get('softClipLevel', 2.5)
            self.assertGreater(out(top, p), white)
            self.assertLess(out(top, p), white + 0.4)
            self.assertAlmostEqual(min(slopes(p)), T.SM_T5_HL_SMIN, delta=0.01)

    def test_the_top_follows_the_exposure_index(self):
        """Half the EI lowers what the camera recorded by a stop: that top lands on Bianco instead."""
        p = curve({'toneHighlights': -100}, expo=0.5)
        self.assertAlmostEqual(out(T.SM_T5_HL_TOP - 1.0, p), 2.5, places=6)

    def test_a_high_bianco_still_leaves_a_real_pull(self):
        """A DRT user's Bianco of 5-7 must not switch Highlights off: -100 still lowers the top 1.5 stops."""
        for white, expo in ((7.0, 1.0), (5.0, 0.5), (4.0, 0.25)):
            p = curve({'toneHighlights': -100, 'softClipLevel': white}, expo=expo)
            top = T.SM_T5_HL_TOP + math.log2(expo)
            self.assertAlmostEqual(out(top, p), min(white, top - T.SM_T5_HL_MINPULL), places=6, msg=(white, expo))

    def test_soft_clip_does_not_compress_twice(self):
        """With Soft Clip on the shoulder leaves room for the roof: the top ends a tenth of a stop under Bianco."""
        p = curve({'toneHighlights': -100, 'softClip': 1})
        self.assertAlmostEqual(out(T.SM_T5_HL_TOP, p), 2.4, delta=0.01)

    def test_the_white_taper_sits_where_the_top_lands(self):
        """A Bianco too low to reach must not grey the highlights out: the taper follows the real landing."""
        p = curve({'toneHighlights': -100, 'softClipLevel': 1.0})
        self.assertAlmostEqual(math.log2(p['hlWhiteLin'] / 0.18), out(T.SM_T5_HL_TOP, p), places=5)

    def test_whites_stays_monotone_in_its_own_slider(self):
        """The slots come after the shoulder and their edges go through it: Whites still moves one way (at -100 it
        has little room left: the top moves -0.21 / +0.32 stops, and near its edge the slope limiter caps it)."""
        for e in (2.0, 3.5, 5.0, 6.0):
            prev = None
            for w in range(-100, 101, 10):
                t = out(e, curve({'toneHighlights': -100, 'toneWhites': w}))
                if prev is not None:
                    self.assertGreaterEqual(t, prev, 'Whites %d at %+g stops' % (w, e))
                prev = t
        top = [out(6.0, curve({'toneHighlights': -100, 'toneWhites': w})) for w in (-100, 0, 100)]
        self.assertLess(top[0], top[1] - 0.15)
        self.assertGreater(top[2], top[1] + 0.25)

    def test_texture_softens_like_film(self):
        """A +/-0.1 stop texture on a +4 stop plateau keeps about a sixth of its contrast at -100."""
        p = curve({'toneHighlights': -100})
        factor = (out(4.1, p) - out(3.9, p)) / 0.2
        self.assertLess(factor, 0.3)
        self.assertGreater(factor, 0.1)


class PathToWhite(unittest.TestCase):
    def oklab_hue(self, xyz):
        l = [math.copysign(abs(c) ** (1 / 3), c) for c in dm.mul(C.OKLAB[0], xyz)]
        _, a, b = dm.mul(C.OKLAB[1], l)
        return math.degrees(math.atan2(b, a))

    def test_hue_holds_while_the_colour_goes_to_white(self):
        """2.0.0's straight line in linear light turned orange to salmon and blue to lavender (8-14 degrees)."""
        p = curve({'toneHighlights': -100})
        for rgb in ((1.0, 0.45, 0.1), (0.1, 0.2, 1.0), (0.9, 0.6, 0.45), (1.0, 0.1, 0.1), (0.3, 0.6, 1.0)):
            for stops in (2.0, 3.5, 5.0):
                xyz = dm.mul(dm.MATS[1][0], [c * 0.18 * 2 ** stops for c in rgb])
                got = T.tone5(xyz, p)
                d = (self.oklab_hue(got) - self.oklab_hue(xyz) + 180.0) % 360.0 - 180.0
                self.assertLess(abs(d), 0.5, (rgb, stops, d))

    def colourfulness(self, xyz):
        d = xyz[0] + 15 * xyz[1] + 3 * xyz[2]
        return math.hypot(4 * xyz[0] / d - 0.19783, 9 * xyz[1] / d - 0.46832)

    def test_bright_colours_drift_towards_white_and_never_negative(self):
        p = curve({'toneHighlights': -100})
        rnd = random.Random(3)
        for _ in range(300):
            space = rnd.choice((1, 2))    # colours that start inside Rec.709 or Rec.2020
            lin = [rnd.uniform(0.0, 1.0) * 2 ** rnd.uniform(0, 6) * 0.18 for _ in range(3)]
            xyz = dm.mul(dm.MATS[space][0], lin)
            if xyz[1] <= 0:
                continue
            got = T.tone5(xyz, p)
            rgb = dm.mul(dm.MATS[2][1], xyz)
            n = T.t5_norm(rgb)
            g = 2 ** T.t5_gain(n, p)[0]
            plain = [c * g for c in xyz]
            self.assertLessEqual(self.colourfulness(got), self.colourfulness(plain) + 1e-9, lin)
            self.assertGreaterEqual(min(dm.mul(dm.MATS[space][1], got)), -1e-9, (lin, space))

    def test_leds_past_the_spectral_locus_stay_positive(self):
        """S-Gamut3.Cine reaches past the locus on LEDs and neon: there Oklab's cones go negative, so the path must
        fall back to linear light and never push a channel under zero in the camera gamut."""
        p = dict(curve({'toneHighlights': -100}), outGamut=8)   # the node writing S-Gamut3.Cine, as in YRGB
        for sg3c in ((0.02, 0.05, 1.5), (0.0, 0.02, 1.0), (1.2, 0.0, 1.4), (0.0, 1.0, 0.05), (1.5, 0.02, 0.0)):
            for stops in (1.0, 3.0, 5.0):
                xyz = dm.mul(dm.MATS[8][0], [c * 2 ** stops * 0.18 for c in sg3c])
                got = dm.mul(dm.MATS[8][1], T.tone5(xyz, p))
                self.assertTrue(all(math.isfinite(c) for c in got), (sg3c, stops))
                self.assertGreaterEqual(min(got), -1e-6 * max(got), (sg3c, stops, got))

    def test_non_finite_pixels_pass_through(self):
        for p in (curve({'toneHighlights': -100}), curve({'toneHighlights': 100})):
            for xyz in ([float('inf'), 0.1, 0.1], [float('nan'), 0.1, 0.1], [float('inf')] * 3):
                got = T.tone5(xyz, p)
                self.assertTrue(all(a == b or (a != a and b != b) for a, b in zip(got, xyz)), xyz)
            self.assertTrue(all(math.isfinite(c) for c in T.tone5([1e30, 1e30, 1e30], p)))

    def test_below_grey_the_colour_is_untouched(self):
        p = curve({'toneHighlights': -100})
        xyz = dm.mul(dm.MATS[2][0], [0.12, 0.05, 0.02])
        self.assertEqual(T.tone5(xyz, p), xyz)


if __name__ == '__main__':
    unittest.main()
