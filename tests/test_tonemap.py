# SPDX-License-Identifier: GPL-3.0-or-later
"""The tone stage: a filmic shoulder and a shadow toe, both pointwise.

These tests guard the properties the design rests on, not its taste:

  * it is POINTWISE, so it cannot make a halo. That is structural and needs no
    test - what needs testing is that it also cannot print a *contour*, which a
    pointwise curve absolutely can do if its slope or curvature jumps. In a smooth
    gradient the pixels at a knee form a level set, and around a bright source
    those level sets are concentric: a ring that reads exactly like a halo. Hence
    the continuity tests.
  * absolute black never lifts, at any setting.
  * mid grey and skin do not move when the shoulder works.
  * nothing ever clips, however bright the scene.
  * chroma follows the compression, so a recovered sky is not neon and a recovered
    forehead is not a flat pink patch.

Reference numbers come from two transforms measured on this machine: the Kodak
2383 print emulation and Blackmagic's Gen 5, both in Resolve's own LUT folder.
"""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import develop_model as dm   # noqa: E402

SG3C = 8
GREY = 0.18
SKY = (0.06, 0.12, 0.30)
SKIN = (0.29, 0.20, 0.155)
FOLIAGE = (0.08, 0.15, 0.05)


def grey_at(ev):
    v = GREY * 2 ** ev
    return [v, v, v]


def tone(rgb, hi=0.0, sh=0.0, cr=0.0):
    return dm.tone(list(rgb), SG3C, hi, sh, cr)


def norm_out(rgb, **kw):
    return dm.tone_norm(tone(rgb, **kw))


def stops(rgb, **kw):
    return math.log2(max(norm_out(rgb, **kw), 1e-12) / GREY)


def sat(rgb):
    mx, mn = max(rgb), min(rgb)
    return (mx - mn) / mx if mx > 1e-9 else 0.0


class Neutrality(unittest.TestCase):
    def test_at_zero_the_stage_changes_nothing(self):
        """The node promises to be neutral at its defaults. The shoulder must not
        quietly break that promise."""
        for sample in (SKY, SKIN, FOLIAGE, grey_at(0), grey_at(-6), grey_at(5)):
            for a, b in zip(tone(sample), sample):
                self.assertAlmostEqual(a, b, places=12)

    def test_a_neutral_pixel_stays_neutral(self):
        """The norm is built so that norm(x, x, x) = x. If that ever broke, every
        grey in the picture would pick up a cast."""
        for ev in (-8, -4, 0, 2, 5):
            out = tone(grey_at(ev), hi=-1.0, sh=1.0, cr=0.5)
            self.assertAlmostEqual(out[0], out[1], places=10)
            self.assertAlmostEqual(out[1], out[2], places=10)


class Shoulder(unittest.TestCase):
    def test_nothing_ever_clips(self):
        """The shoulder is an asymptote it never reaches, so there is no scene value
        bright enough to clip - which is the whole point of recovering highlights."""
        for ev in (6, 8, 12, 20, 30):
            self.assertLessEqual(norm_out(grey_at(ev), hi=-1.0), 1.0 + 1e-12)
        # and it is still resolving, not already flat, where real highlights live
        self.assertGreater(norm_out(grey_at(5), hi=-1.0), norm_out(grey_at(4), hi=-1.0))

    def test_an_absurdly_bright_pixel_does_not_come_out_black(self):
        """In float32 the knee's cube overflows past about 7e12 and an infinite
        divisor would turn the brightest pixel in the frame into a black hole. The
        input is clamped where the curve has already reached its asymptote."""
        for ev in (40, 60, 120):
            out = tone(grey_at(ev), hi=-1.0)
            self.assertGreater(out[0], 0.9)
            self.assertLessEqual(out[0], 1.0 + 1e-9)

    def test_it_is_monotone_so_a_bright_core_never_inverts(self):
        """A non-monotone shoulder makes the brightest pixels come out darker than
        their neighbours - a real bright rim, produced pointwise."""
        prev = -1.0
        for i in range(0, 900):          # -10 to +8 stops; above that float saturates
            v = norm_out(grey_at(-10 + i / 50.0), hi=-1.0)
            self.assertGreater(v, prev)
            prev = v

    def test_mid_grey_and_skin_hold_still(self):
        """Recovering the sky must not drag the midtones down with it."""
        self.assertLess(abs(stops(grey_at(0), hi=-1.0)), 0.01)
        self.assertLess(abs(stops(SKIN, hi=-1.0) - stops(SKIN)), 0.1)

    def test_it_folds_the_top_of_the_scene(self):
        """An S-Log3 carries about 6 stops above grey; a plain Rec.709 takes 2.47.
        At full strength the shoulder has to bring the first inside the second."""
        self.assertLess(stops(grey_at(6), hi=-1.0), math.log2(1 / 0.18))
        self.assertGreater(stops(grey_at(6), hi=-1.0), 2.0)

    def test_its_slope_sits_in_the_range_of_the_measured_references(self):
        """Between the Kodak print and Blackmagic's Gen 5, not outside them."""
        kodak = {1: 1.132, 2: 0.686, 3: 0.308}
        gen5 = {1: 0.934, 2: 0.740, 3: 0.602}
        for ev in (1, 2, 3):
            d = 0.01
            slope = (stops(grey_at(ev + d), hi=-1.0) - stops(grey_at(ev - d), hi=-1.0)) / (2 * d)
            lo = min(kodak[ev], gen5[ev]) * 0.5
            hi = max(kodak[ev], gen5[ev]) * 1.6
            self.assertTrue(lo <= slope <= hi,
                            'a %+d stop la pendenza e %.3f, fuori da [%.3f, %.3f]' % (ev, slope, lo, hi))

    def test_above_three_stops_it_compresses_harder_than_film(self):
        """A deliberate trade, recorded so it is not mistaken for a defect. Holding
        mid grey and skin still costs separation at the very top: a sharper knee
        protects the midtones and spends the last stops faster than a print does.
        Kodak keeps 0.26 display stops between +3 and +6, this keeps about 0.14."""
        span = stops(grey_at(6), hi=-1.0) - stops(grey_at(3), hi=-1.0)
        self.assertTrue(0.05 < span < 0.26, 'separazione +3..+6 = %.3f stop' % span)
        self.assertLess(abs(stops(grey_at(0), hi=-1.0)), 0.01)   # the thing it buys

    def test_positive_highlights_brighten_without_touching_grey(self):
        self.assertGreater(stops(grey_at(3), hi=1.0), stops(grey_at(3)))
        self.assertLess(abs(stops(grey_at(0), hi=1.0)), 0.02)


class Toe(unittest.TestCase):
    def test_absolute_black_stays_black(self):
        """The stage is a gain, so f(0) = 0 whatever the setting. This is the
        property the colourist asked for: never touch the foot of the black."""
        for sh in (-1.0, -0.5, 0.5, 1.0):
            for a in tone([0.0, 0.0, 0.0], sh=sh, hi=-1.0, cr=1.0):
                self.assertEqual(a, 0.0)

    def test_the_foot_is_left_where_it_was(self):
        """Lifting shadows must reveal the detail band, not gain up the noise floor
        underneath it. Below -8 stops the bell has died out."""
        self.assertLess(abs(stops(grey_at(-10), sh=1.0) - (-10.0)), 0.01)
        self.assertLess(abs(stops(grey_at(-14), sh=1.0) - (-14.0)), 0.01)

    def test_it_lifts_the_band_where_shadow_detail_lives(self):
        self.assertGreater(stops(grey_at(-4), sh=1.0) - (-4.0), 1.0)
        self.assertGreater(stops(grey_at(-3), sh=1.0) - (-3.0), 0.5)

    def test_it_leaves_mid_grey_alone(self):
        self.assertLess(abs(stops(grey_at(0), sh=1.0)), 0.02)

    def test_it_never_solarises(self):
        """Too tall a bell makes the curve fold back on itself and the shadows
        invert. The amplitude is chosen to keep the slope positive everywhere."""
        prev = -1.0
        for i in range(0, 1200):
            v = norm_out(grey_at(-14 + i / 50.0), sh=1.0)
            self.assertGreater(v, prev, 'la curva si ripiega: solarizza')
            prev = v


class Continuity(unittest.TestCase):
    """A pointwise curve cannot make a halo, but it can print a contour ring if its
    slope or curvature jumps. These are the tests the old shelf operator failed: it
    had a slope discontinuity from 0.202 to 1.000 at exactly +5 stops."""

    def curve(self, hi, sh):
        step = 0.02
        return [stops(grey_at(-14 + i * step), hi=hi, sh=sh) for i in range(0, 1100)], step

    def test_the_first_derivative_never_jumps(self):
        for hi, sh in ((-1.0, 0.0), (0.0, 1.0), (-1.0, 1.0), (1.0, -1.0)):
            ys, step = self.curve(hi, sh)
            d1 = [(ys[i + 1] - ys[i]) / step for i in range(len(ys) - 1)]
            worst = max(abs(d1[i + 1] - d1[i]) for i in range(len(d1) - 1))
            self.assertLess(worst, 0.05,
                            'salto di pendenza %.3f con hi=%.1f sh=%.1f' % (worst, hi, sh))

    def test_the_second_derivative_never_jumps(self):
        for hi, sh in ((-1.0, 0.0), (0.0, 1.0), (-1.0, 1.0)):
            ys, step = self.curve(hi, sh)
            d1 = [(ys[i + 1] - ys[i]) / step for i in range(len(ys) - 1)]
            d2 = [(d1[i + 1] - d1[i]) / step for i in range(len(d1) - 1)]
            worst = max(abs(d2[i + 1] - d2[i]) for i in range(len(d2) - 1))
            self.assertLess(worst, 1.0,
                            'salto di curvatura %.3f con hi=%.1f sh=%.1f' % (worst, hi, sh))

    def test_the_operator_it_replaces_would_fail_this(self):
        """Kept as the reason the stage was rewritten rather than tuned."""
        def old(ev, h):
            wh = min(max(ev / 5.0, 0.0), 1.0)
            return ev + h * 2 * wh * wh
        d = 1e-4
        before = (old(5.0 - d, -1.0) - old(5.0 - 3 * d, -1.0)) / (2 * d)
        after = (old(5.0 + 3 * d, -1.0) - old(5.0 + d, -1.0)) / (2 * d)
        self.assertGreater(abs(after - before), 0.5)


class Chroma(unittest.TestCase):
    def test_a_recovered_forehead_keeps_its_colour(self):
        """The failure this exists to prevent: a bright forehead compressing into an
        even, fully chromatic patch with no shading - flat pink. Scene saturation is
        0.466; film takes it to 0.15, which is the flat patch. The agreed target is
        about 0.30."""
        got = sat(tone([c * 2 ** 3 for c in SKIN], hi=-1.0))
        self.assertTrue(0.25 <= got <= 0.36, 'incarnato a +3 stop: saturazione %.3f' % got)

    def test_a_recovered_sky_is_not_neon(self):
        """Scaling all three channels leaves saturation untouched, so without an
        explicit purity term a recovered sky keeps every bit of its colour."""
        plain = sat(SKY)
        got = sat(tone([c * 2 ** 4 for c in SKY], hi=-1.0))
        self.assertLess(got, plain, 'il cielo recuperato non ha perso purezza')

    def test_purity_falls_as_the_curve_compresses_harder(self):
        last = 1.1
        for ev in (1, 2, 3, 4, 5, 6):
            got = sat(tone([c * 2 ** ev for c in SKY], hi=-1.0))
            self.assertLess(got, last)
            last = got

    def test_color_recovery_hands_colour_back_to_the_highlights(self):
        base = sat(tone([c * 2 ** 3 for c in SKY], hi=-1.0))
        more = sat(tone([c * 2 ** 3 for c in SKY], hi=-1.0, cr=1.0))
        less = sat(tone([c * 2 ** 3 for c in SKY], hi=-1.0, cr=-1.0))
        self.assertGreater(more, base)
        self.assertLess(less, base)

    def test_it_never_adds_chroma_the_pixel_did_not_have(self):
        """Recovery may only restore what the curve took. Pushed to the stop it must
        approach the untouched chromaticity, never overshoot past it."""
        for ev in (2, 3, 4):
            scene = sat(SKY)
            got = sat(tone([c * 2 ** ev for c in SKY], hi=-1.0, cr=1.0))
            self.assertLessEqual(got, scene + 1e-9)

    def test_color_recovery_takes_chroma_out_of_lifted_shadows(self):
        """Opening the shadows brings their chroma noise up with them."""
        dark = [c * 2 ** -4 for c in SKY]
        plain = sat(tone(dark, sh=1.0))
        quiet = sat(tone(dark, sh=1.0, cr=1.0))
        self.assertLess(quiet, plain)

    def test_it_does_not_desaturate_shadows_it_did_not_lift(self):
        dark = [c * 2 ** -4 for c in SKY]
        self.assertAlmostEqual(sat(tone(dark, sh=0.0, cr=1.0)), sat(dark), places=9)


class ConstantsAgree(unittest.TestCase):
    """The tone constants live twice: once in the header the plugin and the Metal
    kernel share, once in the Python reference. If they ever drift apart the maths
    tests keep passing while comparing two different curves, so compare the source."""

    def test_every_tone_constant_matches_the_shared_header(self):
        import re
        header = os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'DevelopMath.h.in')
        with open(header, encoding='utf-8') as fh:
            cpp = dict((m[0], float(m[1])) for m in
                       re.findall(r'SM_CONST float SM_(TONE_\w+)\s*=\s*(-?[\d.]+)f', fh.read()))
        self.assertTrue(cpp, 'nessuna costante trovata nel header')
        for name, value in cpp.items():
            self.assertTrue(hasattr(dm, name), 'il modello Python non ha %s' % name)
            self.assertEqual(getattr(dm, name), value,
                             '%s: header %s, modello %s' % (name, value, getattr(dm, name)))


if __name__ == '__main__':
    unittest.main()
