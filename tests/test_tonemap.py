# SPDX-License-Identifier: GPL-3.0-or-later
"""The tone stage: a press that comes down from the top of the linear tank.

These tests guard the properties the design rests on, not its taste:

  * MONOTONE, per channel, everywhere. This is the one that matters. The version
    before this scaled the three channels by f(norm)/norm and then pulled them
    towards luminance by purity = t^k(t); once f reached its asymptote it was flat
    while purity kept falling, so a brighter chromatic pixel came out DARKER - the
    top of a sky read as a negative. It is now structural: two branches that are
    each monotone in every channel, blended with a weight that does not depend on
    the pixel.
  * it is POINTWISE, so it cannot make a halo. That is structural and needs no
    test - what needs testing is that it also cannot print a *contour*, which a
    pointwise curve absolutely can do if its slope or curvature jumps. In a smooth
    gradient the pixels at a knee form a level set, and around a bright source
    those level sets are concentric: a ring that reads exactly like a halo. Hence
    the continuity tests.
  * the ceiling is LINEAR in the slider and anchored to the container the camera
    recorded, never to the picture.
  * absolute black never lifts, at any setting.
  * mid grey and skin do not move when the press works.
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
SLOG3 = 9
GREY = 0.18
E_TOP = dm.tank_top(SLOG3)          # +7.738 stops: the container an S-Log3 clip has
E_709 = dm.TONE_E_709
SKY = (0.06, 0.12, 0.30)
SKIN = (0.29, 0.20, 0.155)
FOLIAGE = (0.08, 0.15, 0.05)
# every direction the sweeps ride, including primaries with a channel at exactly
# zero - the case a level-dependent saturation move inverts first
RAYS = ((1, 1, 1), SKY, SKIN, FOLIAGE, (1, .3, .25), (.2, 1, .35), (1, .95, .2),
        (1, .2, 1), (.05, .1, 1), (1, .5, 0), (0, .4, 1), (1, 0, 0), (0, 0, 1),
        (0, 1, 0), (1, 1, 0))


def grey_at(ev):
    v = GREY * 2 ** ev
    return [v, v, v]


def tone(rgb, hi=0.0, sh=0.0, cr=0.0, e_top=E_TOP):
    return dm.tone(list(rgb), SG3C, hi, sh, cr, e_top)


def norm_out(rgb, **kw):
    return dm.tone_norm(tone(rgb, **kw))


def stops(rgb, **kw):
    return math.log2(max(norm_out(rgb, **kw), 1e-12) / GREY)


def sat(rgb):
    mx, mn = max(rgb), min(rgb)
    return (mx - mn) / mx if mx > 1e-9 else 0.0


class Neutrality(unittest.TestCase):
    def test_at_zero_the_stage_changes_nothing(self):
        """The node promises to be neutral at its defaults, and the press must not
        quietly break that promise. Highlights at 0 puts the asymptote at 0, which
        every caller reads as 'identity' - there is no near-miss to tolerate."""
        for sample in (SKY, SKIN, FOLIAGE, grey_at(0), grey_at(-6), grey_at(5)):
            for cr in (-1.0, 0.0, 1.0):
                for a, b in zip(tone(sample, cr=cr), sample):
                    self.assertEqual(a, b)

    def test_a_neutral_pixel_stays_neutral(self):
        """The norm is built so that norm(x, x, x) = x. If that ever broke, every
        grey in the picture would pick up a cast."""
        for ev in (-8, -4, 0, 2, 5):
            out = tone(grey_at(ev), hi=-1.0, sh=1.0, cr=0.5)
            self.assertAlmostEqual(out[0], out[1], places=10)
            self.assertAlmostEqual(out[1], out[2], places=10)


class Monotone(unittest.TestCase):
    """The defect this release exists to fix. A pointwise curve that is not monotone
    makes the brightest pixels come out darker than their neighbours: the top of a
    sky, a neon sign or a lamp reads as a negative, and no amount of grading gets it
    back. It has to hold per CHANNEL, on every chromaticity, at every setting."""

    def sweep(self, hi, sh, cr, ray, steps=161):
        prev, bad = None, []
        for i in range(steps):
            t = 2 ** ((i / (steps - 1.0)) * 26 - 11)
            out = tone([c * t * GREY for c in ray], hi=hi, sh=sh, cr=cr)
            if prev is not None:
                for ch in range(3):
                    if out[ch] < prev[ch] - 1e-12:
                        bad.append((round(math.log2(t), 2), ch, prev[ch] - out[ch]))
            prev = out
        return bad

    def test_no_chromaticity_ever_inverts(self):
        for hi in (-1.0, -0.75, -0.5, -0.25, -0.1, 0.25, 0.5, 1.0):
            for sh in (-1.0, 0.0, 1.0):
                for cr in (-1.0, 0.0, 1.0):
                    for ray in RAYS:
                        bad = self.sweep(hi, sh, cr, ray)
                        self.assertEqual(bad, [], 'hi=%.2f sh=%.1f cr=%.1f ray=%s: %s'
                                         % (hi, sh, cr, ray, bad[:3]))

    def test_the_stage_it_replaces_would_fail_this(self):
        """Kept as the reason the stage was rewritten rather than tuned: the old
        ratio-plus-purity pair inverted a saturated blue ramp from +4.2 stops at
        Highlights -100, and from +7.2 stops at -10, which is inside what an S-Log3
        records."""
        def old(rgb, hi):
            norm = dm.tone_norm(rgb)
            if norm <= 1e-6:
                return list(rgb)
            a = -hi
            t = (norm ** -3.0 + a ** 3.0) ** (-1 / 3.0) / norm
            out = [c * t for c in rgb]
            k = 0.5 * (1.0 + max(1.0 - t, 0.0))
            purity = t ** k if t < 1 else 1.0
            if purity < 1.0:
                yl = dm.mul(dm.MATS[SG3C][0], out)[1]
                out = [yl + (c - yl) * purity for c in out]
            return out
        for hi in (-0.1, -1.0):
            inverted = False
            prev = None
            for i in range(200):
                t = 2 ** (i / 10.0 - 4)
                out = old([c * t for c in (0.35, 0.55, 1.0)], hi)
                if prev is not None and out[2] < prev[2] - 1e-9:
                    inverted = True
                prev = out
            self.assertTrue(inverted, 'il vecchio stadio a hi=%.1f non inverte' % hi)


class Press(unittest.TestCase):
    def test_minus_one_hundred_lands_the_container_on_the_rec709_peak(self):
        """The endpoint the whole parameterisation is built around: at -100 the top
        of the recorded container sits exactly on 1.0 linear, the brightest value a
        Rec.709 signal can carry."""
        top = dm.tone_curve(GREY * 2 ** E_TOP, dm.tone_asymptote(E_TOP, -1.0), 0.0, 0)
        self.assertAlmostEqual(top, 1.0, places=5)
        self.assertAlmostEqual(math.log2(top / GREY), E_709, places=4)

    def test_the_ceiling_is_linear_in_the_slider(self):
        """The old law put the asymptote at 1/|H| linear: the first ten points of
        travel moved the ceiling from infinity to +5.8 stops and the remaining
        ninety were worth 3.3 stops between them, which is what made it unusable
        'after a few clicks'. The ceiling now moves by equal steps."""
        ceil = [dm.tone_ceiling(E_TOP, -h / 100.0) for h in range(0, 101)]
        steps = [ceil[i] - ceil[i + 1] for i in range(100)]
        self.assertAlmostEqual(min(steps), max(steps), places=9)
        self.assertAlmostEqual(ceil[0], E_TOP, places=9)
        self.assertAlmostEqual(ceil[100], E_709, places=9)

    def test_the_container_is_the_curve_the_camera_recorded(self):
        """Never the picture, and never the timeline: a property of the format, so
        the same number on every frame of every clip shot that way."""
        self.assertAlmostEqual(dm.tank_top(SLOG3), 7.738, places=2)
        self.assertAlmostEqual(dm.tank_top(8), 6.256, places=2)      # S-Log2
        self.assertAlmostEqual(dm.tank_top(7), 5.757, places=2)      # S-Log
        for g in (1, 2, 3, 4, 5, 6):   # linear and the display curves have no ceiling
            self.assertEqual(dm.tank_top(g), dm.TONE_E_TOP_DEF)

    def test_nothing_ever_clips(self):
        """The press folds towards an asymptote it never reaches, so there is no
        scene value bright enough to clip - the whole point of recovering
        highlights. The asymptote sits a hair above the ceiling, because the curve
        is pinned to send the top of the container exactly onto it."""
        k = dm.tone_asymptote(E_TOP, -1.0)
        for ev in (6, 8, 12, 20, 30):
            # equal only where x^-n has underflowed to zero, which is the designed
            # landing: the soft-minimum form puts an absurd value exactly on K
            # instead of overflowing the way x/(1+(x/K)^n)^(1/n) would
            self.assertLessEqual(norm_out(grey_at(ev), hi=-1.0), k)
        # and it is still resolving, not already flat, where real highlights live
        self.assertGreater(norm_out(grey_at(5), hi=-1.0), norm_out(grey_at(4), hi=-1.0))

    def test_an_absurdly_bright_pixel_does_not_come_out_black(self):
        """Written as (x^-n + K^-n)^(-1/n), a huge x underflows to 0 and lands on the
        asymptote. Written as x/(1+(x/K)^n)^(1/n) it would overflow float32 and the
        infinite divisor would turn the brightest pixel in the frame black."""
        k = dm.tone_asymptote(E_TOP, -1.0)
        for ev in (40, 60, 120):
            out = tone(grey_at(ev), hi=-1.0)
            self.assertGreater(out[0], 0.9)
            self.assertLessEqual(out[0], k)

    def test_mid_grey_and_skin_hold_still(self):
        """Pressing the sky down must not drag the midtones with it. Measured at
        Highlights -100 on an S-Log3 container: grey 0.008 stop, skin 0.043."""
        self.assertLess(abs(stops(grey_at(0), hi=-1.0)), 0.02)
        self.assertLess(abs(stops(SKIN, hi=-1.0) - stops(SKIN)), 0.1)

    def test_it_folds_the_top_of_the_scene(self):
        """An S-Log3 carries 7.7 stops above grey; a plain Rec.709 takes 2.47. At
        full strength the press has to bring the first inside the second."""
        self.assertLessEqual(stops(grey_at(E_TOP), hi=-1.0), E_709 + 1e-3)
        self.assertGreater(stops(grey_at(E_TOP), hi=-1.0), 2.0)

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

    def test_it_keeps_detail_between_three_stops_and_the_top(self):
        """What the knee exponent buys. At Highlights -100 the range from +3 stops to
        the top of the container has to stay readable rather than being piled against
        the ceiling: n = 3 left 0.139 stop there, n = 2.5 leaves 0.195."""
        span = stops(grey_at(E_TOP), hi=-1.0) - stops(grey_at(3), hi=-1.0)
        self.assertTrue(0.15 < span < 0.30, 'separazione +3..top = %.3f stop' % span)
        self.assertLess(abs(stops(grey_at(0), hi=-1.0)), 0.02)   # the thing it buys


class Expansion(unittest.TestCase):
    def test_positive_highlights_stretch_the_top_without_touching_grey(self):
        self.assertGreater(stops(grey_at(5), hi=1.0), stops(grey_at(5)))
        self.assertGreater(stops(grey_at(3), hi=1.0), stops(grey_at(3)))
        self.assertLess(abs(stops(grey_at(0), hi=1.0)), 0.02)

    def test_the_lift_is_strictly_bounded(self):
        """The exact inverse of an asymptotic curve diverges as it approaches the
        asymptote, and the asymptote sits BELOW the top of the container - so the
        whole upper part of the frame would hit a wall and come out as one flat
        value. Measured before the cap: S-Log3 code 0.80 came out at 1.145 at
        Highlights +50, with everything above it on the same number."""
        for h in (0.25, 0.5, 0.75, 1.0):
            k = dm.tone_asymptote(E_TOP, h)
            cap = h * dm.TONE_EXPAND
            worst = max(dm.tone_curve(GREY * 2 ** (e / 8.0), k, cap, 1) / (GREY * 2 ** (e / 8.0))
                        for e in range(-80, 200))
            self.assertLess(worst, 2 ** cap + 1e-6)

    def test_it_is_the_mirror_of_the_press(self):
        """Same displacement law, opposite sign: what the press takes off a value at
        a given level, the expansion puts back on, up to the cap."""
        for h in (0.1, 0.3):
            x = GREY * 2 ** 4
            down = dm.tone_curve(x, dm.tone_asymptote(E_TOP, -h), 0.0, 0)
            up = dm.tone_curve(x, dm.tone_asymptote(E_TOP, h), h * dm.TONE_EXPAND, 1)
            self.assertAlmostEqual(math.log2(x / down), math.log2(up / x), places=3)


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

    def test_its_centre_is_anchored_to_the_floor_of_the_tank(self):
        self.assertEqual(dm.TONE_E_BOT + dm.TONE_SHAD_OFF, -4.0)

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
    had a slope discontinuity from 0.202 to 1.000 at exactly +5 stops. They are also
    what caught the hard min(drop, cap) the expansion was first written with, which
    jumped 0.589 at Highlights +100."""

    def curve(self, hi, sh):
        step = 0.02
        return [stops(grey_at(-14 + i * step), hi=hi, sh=sh) for i in range(0, 1100)], step

    def test_the_first_derivative_never_jumps(self):
        for hi, sh in ((-1.0, 0.0), (0.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0),
                       (0.5, 0.0), (-0.25, 0.0)):
            ys, step = self.curve(hi, sh)
            d1 = [(ys[i + 1] - ys[i]) / step for i in range(len(ys) - 1)]
            worst = max(abs(d1[i + 1] - d1[i]) for i in range(len(d1) - 1))
            self.assertLess(worst, 0.05,
                            'salto di pendenza %.3f con hi=%.1f sh=%.1f' % (worst, hi, sh))

    def test_the_second_derivative_never_jumps(self):
        for hi, sh in ((-1.0, 0.0), (0.0, 1.0), (-1.0, 1.0), (1.0, 0.0)):
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
    """Color Recovery is the weight between the two branches: the ratio-preserving
    one, which keeps every bit of the colour the pixel had, and the per-channel one,
    where the three channels share a ceiling and converge climbing towards it -
    because converging IS desaturating, which is how film does it."""

    def test_a_recovered_forehead_keeps_its_colour(self):
        """The failure this exists to prevent: a bright forehead compressing into an
        even, fully chromatic patch with no shading - flat pink. Scene saturation is
        0.466; film takes it to 0.15, which is the flat patch."""
        got = sat(tone([c * 2 ** 3 for c in SKIN], hi=-1.0))
        self.assertTrue(0.25 <= got <= 0.42, 'incarnato a +3 stop: saturazione %.3f' % got)

    def test_a_recovered_sky_is_not_neon(self):
        """Scaling all three channels leaves saturation untouched, so a purely
        ratio-preserving press would give the sky back at full scene chroma."""
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

    def test_it_is_monotone_in_the_slider(self):
        """The control has to be steerable: every step to the right gives more
        colour back, with no reversal in the middle."""
        for ev in (2, 4, 6):
            last = -1.0
            for i in range(41):
                got = sat(tone([c * 2 ** ev for c in SKY], hi=-1.0, cr=-1.0 + i / 20.0))
                self.assertGreater(got, last - 1e-12)
                last = got

    def test_it_never_adds_chroma_the_pixel_did_not_have(self):
        """Recovery may only restore what the curve took. Pushed to the stop it
        reaches the ratio-preserving branch, which is the scene chromaticity, and
        stops there."""
        for ev in (2, 3, 4):
            scene = sat(SKY)
            got = sat(tone([c * 2 ** ev for c in SKY], hi=-1.0, cr=1.0))
            self.assertLessEqual(got, scene + 1e-9)

    def test_it_does_nothing_where_the_press_did_nothing(self):
        """No press, no chroma move: the control trims what the compression took,
        it is not a saturation slider in disguise."""
        dark = [c * 2 ** -4 for c in SKY]
        for cr in (-1.0, 1.0):
            self.assertAlmostEqual(sat(tone(dark, sh=1.0, cr=cr)), sat(tone(dark, sh=1.0)),
                                   places=9)


class NoBlowUps(unittest.TestCase):
    """Every control at both ends at once, on the values a real clip carries plus a
    few that no clip does. The node has to stay a node."""

    def test_nothing_is_nan_or_infinite(self):
        for hi in (-1.0, 0.0, 1.0):
            for sh in (-1.0, 1.0):
                for cr in (-1.0, 1.0):
                    for ev in (-40, -14, -6, 0, 3, 8, 20, 60):
                        for ray in RAYS:
                            out = tone([c * GREY * 2 ** ev for c in ray], hi=hi, sh=sh, cr=cr)
                            for v in out:
                                self.assertFalse(math.isnan(v) or math.isinf(v),
                                                 'hi=%.0f sh=%.0f cr=%.0f ev=%d %s' %
                                                 (hi, sh, cr, ev, ray))

    def test_a_channel_never_changes_sign(self):
        """A wide gamut hands this stage negative channels. Whatever it does to them
        it may not flip one, and it may not push a positive one through black - which
        is what blending towards the Y of a wide gamut used to do, that Y being
        negative for a saturated blue."""
        for hi in (-1.0, -0.5, 0.5, 1.0):
            for cr in (-1.0, 0.0, 1.0):
                for ray in ((1, -0.05, -0.02), (-0.1, 0.2, 1.0), (0.4, -0.3, 0.9)):
                    for ev in (-4, 0, 4, 8):
                        out = tone([c * GREY * 2 ** ev for c in ray], hi=hi, cr=cr)
                        for a, b in zip(out, ray):
                            self.assertGreaterEqual(a * b, 0.0, 'segno invertito su %s' % (ray,))

    def test_the_whole_develop_survives_every_extreme(self):
        for hi in (-1.0, 1.0):
            for sh in (-1.0, 1.0):
                for co in (-1.0, 1.0):
                    for sa in (-1.0, 1.0):
                        for bo in (-1.0, 1.0):
                            for cv in (0.0, 0.05, 0.41, 0.9, 1.0):
                                out = dm.develop([cv, cv * 0.3, cv * 0.1], SG3C, SLOG3,
                                                 highlights=hi, shadows=sh, contrast=co,
                                                 saturation=sa, boost=bo, chroma_recover=1.0)
                                for v in out:
                                    self.assertFalse(math.isnan(v) or math.isinf(v))


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
