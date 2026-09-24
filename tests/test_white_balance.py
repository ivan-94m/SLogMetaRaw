# SPDX-License-Identifier: GPL-3.0-or-later
"""Color Temp and Tint: every slider position is a real white, and each slider only ever pushes one way.

2.0.0 reversed in places: the Kim et al. locus had seams at 2222 K and 4000 K, and a green tint at low
Kelvin drove the white's Bradford S cone through zero, so the adaptation turned inside out (an FX6 at
3200 K with its tint misread as +100 sat exactly there). The checks below are on the white itself, in
the Bradford cone space the adaptation divides by, so they hold whatever the as-shot white is.
"""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import develop_model as dm  # noqa: E402
from slogmetaraw import rtmd  # noqa: E402

KELVINS = list(range(2000, 15001, 25))
TINTS = list(range(-100, 101))


def lms(k, t):
    return dm.mul(dm.BR, dm.white_xyz(k, t))


class Whites(unittest.TestCase):
    def test_every_white_the_sliders_reach_is_a_real_one(self):
        for k in range(1500, 15001, 100):
            for t in range(-150, 151, 10):
                self.assertGreater(min(lms(k, t)), 0.0, '%d K tint %+d' % (k, t))

    def test_raising_color_temp_always_warms(self):
        """The adaptation multiplies by as-shot / chosen: a bluer chosen white (S/L up) warms the picture."""
        for t in range(-100, 101, 10):
            prev = None
            for k in KELVINS:
                L, M, S = lms(k, t)
                if prev is not None:
                    self.assertGreater(S / L, prev, '%d K tint %+d' % (k, t))
                prev = S / L

    def test_raising_tint_always_adds_magenta(self):
        """A greener chosen white (M against L and S) takes green out of the picture."""
        for k in list(range(2000, 4001, 50)) + list(range(4500, 15001, 500)):
            prev = None
            for t in TINTS:
                L, M, S = lms(k, t)
                q = M / math.sqrt(L * S)
                if prev is not None:
                    self.assertGreater(q, prev, '%d K tint %+d' % (k, t))
                prev = q

    def test_no_seam_along_the_locus(self):
        """The slope of the locus changes smoothly: no jump where Kim et al. switched polynomials."""
        def step(k):
            (u0, v0, _), (u1, v1, _) = dm.locus_uv(k), dm.locus_uv(k + 10)
            return math.hypot(u1 - u0, v1 - v0)
        for k in (2212, 2222, 2232, 3990, 4000, 4010):
            self.assertAlmostEqual(step(k) / step(k - 10), 1.0, delta=0.01, msg='%d K' % k)

    def test_green_tint_is_untouched_where_it_is_safe(self):
        """The guard only works at low Kelvin: at daylight every slider value is the plain Duv * 3000."""
        for k in (5600, 6500, 10000):
            u, v, n = dm.locus_uv(k)
            for t in (-100, -30, 30, 95):
                x, y = dm.uv_xy(u + n[0] * t / 3000, v + n[1] * t / 3000)
                self.assertEqual(dm.white_xyz(k, t), [x / y, 1.0, (1 - x - y) / y])


class AdaptedNeutral(unittest.TestCase):
    """What the colourist sees: a grey card, as shot, moved by the sliders."""

    def test_an_fx6_at_3200k_follows_the_tint_slider(self):
        for shot_tint in (3.03, 15.17, -20.0):
            prev = None
            for t in TINTS:
                v = dm.neutral_uv(3200, shot_tint, 3200, t)[1]
                if prev is not None:
                    self.assertLess(v, prev, 'shot tint %g, slider %+d' % (shot_tint, t))
                prev = v

    def test_as_shot_is_neutral(self):
        for shot in ((2000, 0), (3200, 15.17), (5600, 4.55), (15000, -99)):
            u, v = dm.neutral_uv(*shot, *shot)
            self.assertAlmostEqual(u, 0.19783, places=4)
            self.assertAlmostEqual(v, 0.31221, places=4)


class SonyTint(unittest.TestCase):
    def test_the_file_stores_hundredths(self):
        """FX6_0024.MXF carries 455 and the camera shows 4.55; 1517 is 15.17 in Catalyst Browse and Resolve."""
        decode = rtmd.TAGS[0x811f][2]
        self.assertEqual(decode(bytes.fromhex('01c7')), 4.55)
        self.assertEqual(decode(bytes.fromhex('05ed')), 15.17)
        self.assertEqual(decode(bytes.fromhex('fed4')), -3.0)


if __name__ == '__main__':
    unittest.main()
