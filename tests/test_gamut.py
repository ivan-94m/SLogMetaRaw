# SPDX-License-Identifier: GPL-3.0-or-later
"""The gamut stage: whatever we write to, write something that can exist there.

Reported on a concert shot on an FX30, with strong saturated stage LEDs: "however I
turn it the lights and the colours fall apart", and on the waveform the blue folding
back under itself. Four screenshots with the node set to output Rec.709, and a fifth
with it set to DaVinci WG where the same frame is clean - which is the diagnosis:
it is the matrix, not the curve.

A saturated blue LED, [0.02 0.05 1.50] in S-Gamut3.Cine linear, converts to Rec.709
as R -0.125, G -0.292. Negative before the tone stage has any say, because that
colour is outside Rec.709. And the press cannot repair it: it multiplies the three
channels by one POSITIVE factor, so it can walk a negative towards zero and never
through it - Highlights at -100 takes that -0.125 only to -0.072.

The measurements in here are the ones from that investigation, so if the stage is
ever retuned the numbers move with it and the trade stays visible.
"""
import math
import os
import random
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import develop_model as dm  # noqa: E402

SG3C, R709, DWG = 8, 1, 0
SLOG3 = 9
BLUE_LED = [0.02, 0.05, 1.50]        # the reported light
SKIN = [0.29, 0.20, 0.155]
GREY = [0.18, 0.18, 0.18]


def to(space, lin, frm=SG3C):
    return dm.mul(dm.MATS[space][1], dm.mul(dm.MATS[frm][0], lin))


class TheReportedCase(unittest.TestCase):
    def test_the_conversion_is_what_makes_it_negative(self):
        """Kept as the reason this stage exists: the tone press is not involved."""
        o = to(R709, BLUE_LED)
        self.assertLess(o[0], 0.0)
        self.assertLess(o[1], 0.0)
        self.assertAlmostEqual(o[0], -0.125, places=2)
        self.assertAlmostEqual(o[1], -0.292, places=2)

    def test_the_press_could_never_have_fixed_it(self):
        """One positive factor on all three channels walks a negative towards zero
        and never through it."""
        e_top = dm.tank_top(SLOG3)
        for h in (0.0, -0.5, -1.0):
            o = to(R709, dm.tone(BLUE_LED, SG3C, h, 0.0, 0.0, e_top))
            self.assertLess(o[0], 0.0, 'Highlights %.0f: R = %.4f' % (h * 100, o[0]))

    def test_the_same_frame_to_davinci_wg_was_already_clean(self):
        """Which is what the fifth screenshot shows, and why the waveform behaved."""
        self.assertGreater(min(to(DWG, BLUE_LED)), 0.0)

    def test_it_comes_out_positive_now(self):
        o = dm.gamut_compress(to(R709, BLUE_LED))
        self.assertGreater(min(o), 0.0)

    def test_the_whole_develop_writes_nothing_negative(self):
        cv = [dm.encode1(c, SLOG3) for c in BLUE_LED]
        out = dm.develop(cv, SG3C, SLOG3, out_space=R709, out_gamma=5)
        self.assertGreater(min(out), 0.0, 'code value negativi in uscita: %s' % out)


class TheGuarantee(unittest.TestCase):
    def test_no_pixel_comes_out_negative(self):
        """The property the whole stage is for. Brute force, including pixels far
        outside anything a real camera produces."""
        rnd = random.Random(11)
        for _ in range(200000):
            c = [rnd.uniform(-3.0, 6.0) for _ in range(3)]
            g = dm.gamut_compress(c)
            if max(c) > 1e-9:
                self.assertGreaterEqual(min(g), 0.0, '%s -> %s' % (c, g))

    def test_the_largest_channel_never_moves(self):
        """Only chroma travels, never the level: what the press decided about
        brightness has to survive this stage untouched."""
        rnd = random.Random(12)
        for _ in range(50000):
            c = [rnd.uniform(-3.0, 6.0) for _ in range(3)]
            if max(c) <= 1e-9:
                continue
            self.assertAlmostEqual(max(dm.gamut_compress(c)), max(c), places=12)

    def test_the_order_of_the_channels_is_kept(self):
        """If the ranking changed, the hue would swing."""
        rnd = random.Random(13)
        for _ in range(50000):
            c = [rnd.uniform(-3.0, 6.0) for _ in range(3)]
            if max(c) <= 1e-9:
                continue
            g = dm.gamut_compress(c)
            self.assertEqual(sorted(range(3), key=lambda i: c[i]),
                             sorted(range(3), key=lambda i: g[i]), '%s -> %s' % (c, g))

    def test_it_is_monotone_along_a_ray(self):
        for d in (BLUE_LED, SKIN, [1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [1.0, 1.0, 0.0]):
            base = to(R709, d)
            prev = None
            for i in range(400):
                s = 2 ** ((i / 399.0) * 20 - 10)
                g = dm.gamut_compress([c * s for c in base])
                if prev is not None:
                    for k in range(3):
                        self.assertGreaterEqual(g[k], prev[k] - 1e-12)
                prev = g

    def test_nothing_is_nan(self):
        rnd = random.Random(14)
        edge = [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [1e-9, 0.0, 0.0], [-1.0, -1.0, -1.0],
                [1e9, 1.0, -1e9], [0.7, 0.7, 0.7]]
        for c in edge + [[rnd.uniform(-9, 9) for _ in range(3)] for _ in range(20000)]:
            for v in dm.gamut_compress(c):
                self.assertFalse(math.isnan(v) or math.isinf(v), c)


class InsideTheGamutNothingHappens(unittest.TestCase):
    def test_a_grey_does_not_move_by_a_bit(self):
        for ev in range(-10, 11):
            v = 0.18 * 2 ** ev
            self.assertEqual(dm.gamut_compress([v, v, v]), [v, v, v])

    def test_skin_does_not_move_by_a_bit(self):
        for ev in (-3, 0, 2, 5):
            px = to(R709, [c * 2 ** ev for c in SKIN])
            self.assertEqual(dm.gamut_compress(px), px)

    def test_a_normal_shot_never_even_reaches_the_threshold(self):
        """The regression that matters for every ordinary shot. Stated exactly: for
        an in-gamut colour every channel sits closer to the achromatic than the
        threshold, so the stage provably cannot touch it - not "changes it by very
        little", cannot touch it."""
        for cv in (0.3, 0.41, 0.6, 0.8, 1.0):
            for tilt in (1.0, 0.92, 0.75):
                px = [dm.decode1(cv, SLOG3) * f for f in (1.0, tilt, tilt * 0.9)]
                lin = to(R709, px)
                ac = max(lin)
                for v in lin:
                    self.assertLess((ac - v) / ac, dm.GAMUT_THRESH)
                self.assertEqual(dm.gamut_compress(lin), lin)


class TheDeclaredTrade(unittest.TestCase):
    """A threshold below 1 moves colours that are legitimately inside the gamut, and
    the number is worth pinning: it was chosen for the gentlest re-entry, and no
    control gives it back. Color Recovery is the weight between the two branches
    INSIDE the press, which runs before the conversion, so it cannot see this stage.
    """

    def test_a_pure_primary_pays_six_percent(self):
        g = dm.gamut_compress([1.0, 0.0, 0.0])
        self.assertAlmostEqual(g[1], 0.062, places=2)
        self.assertAlmostEqual(g[1], g[2], places=12)
        self.assertEqual(g[0], 1.0)

    def test_the_threshold_is_where_it_says_it_is(self):
        """Below it, identity; above it, movement. No third behaviour."""
        t = dm.GAMUT_THRESH
        for d in (0.0, 0.3, t - 0.01):
            v = 1.0 - d                      # ac = 1, so d is the distance directly
            self.assertEqual(dm.gamut_compress([1.0, v, v])[1], v)
        for d in (t + 0.05, 0.95, 1.2):
            v = 1.0 - d
            self.assertGreater(dm.gamut_compress([1.0, v, v])[1], v)

    def test_the_constants_match_the_shared_header(self):
        header = os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'DevelopMath.h.in')
        with open(header, encoding='utf-8') as fh:
            cpp = dict((m[0], float(m[1])) for m in
                       re.findall(r'SM_CONST float SM_GAMUT_(\w+)\s*=\s*(-?[\d.]+)f', fh.read()))
        self.assertEqual(cpp, {'THRESH': dm.GAMUT_THRESH, 'KNEE': dm.GAMUT_KNEE})


if __name__ == '__main__':
    unittest.main()
