# SPDX-License-Identifier: GPL-3.0-or-later
"""The three false colours: what each band means, and whether the readout is true.

The exposure view follows the ARRI ALEXA convention (green on 18% grey, pink one
stop over it, yellow approaching clip, red clipped, blue and purple at the bottom).
The two white-balance views are calibrated in the units of their own sliders, so a
band is not just "some cast" but "this slider is this far from neutral" - which is
what these tests check, against the real develop path.
"""
import math
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import develop_model as dm   # noqa: E402

SG3C, SLOG3, DWG, ACESCCT = 8, 9, 0, 10
WHITE = [0.95, 0.95, 0.95]
GREEN = [0.13, 0.82, 0.20]
PINK = [1.00, 0.56, 0.72]
RED = [0.96, 0.16, 0.10]
YELLOW = [1.00, 0.88, 0.12]
BLUE = [0.10, 0.28, 0.88]
PURPLE = [0.42, 0.12, 0.62]
DARK = [0.11, 0.11, 0.13]


def grey_card(shot_k, shot_t, k, t, stops=0.0):
    """A neutral surface as the camera recorded it, seen through the node."""
    code = dm.encode1(0.18 * (2 ** stops), SLOG3)
    out = dm.develop([code] * 3, SG3C, SLOG3, shot=(shot_k, shot_t, 800), temp=k, tint=t)
    lin = [dm.decode1(c, SLOG3) for c in out]
    return dm.mul(dm.MATS[SG3C][0], lin)


def view(xyz, mode, k, t):
    return dm.false_color(xyz, mode, *dm.fc_calibration(k, t))


def readout(mode, shot_k, shot_t, k, t):
    """The raw number behind a band: how far this slider is from neutral."""
    u0, v0, ku, kv, tu, tv = dm.fc_calibration(k, t)
    X, Y, Z = grey_card(shot_k, shot_t, k, t)
    d = X + 15 * Y + 3 * Z
    du, dv = 4 * X / d - u0, 6 * Y / d - v0
    return -(ku * du + kv * dv), -(tu * du + tv * dv)


class ExposureView(unittest.TestCase):
    def test_the_anchors_of_the_arri_convention(self):
        for stops, want, what in ((0.0, GREEN, '18% grey'), (1.0, PINK, 'skin, a stop over grey'),
                                  (6.0, RED, 'clipped'), (4.5, YELLOW, 'a stop from clip'),
                                  (-5.0, BLUE, 'deep shadow'), (-7.0, PURPLE, 'black clip')):
            self.assertEqual(dm.fc_exposure(stops), want, what)

    def test_the_bands_are_narrow_and_everything_else_stays_monochrome(self):
        for stops in (-3.0, -1.0, 0.5, 2.0, 3.0):
            c = dm.fc_exposure(stops)
            self.assertEqual(c[0], c[1], 'at %+.1f stop the picture must stay readable' % stops)
            self.assertEqual(c[1], c[2])

    def test_the_grey_ramp_climbs_with_the_stops(self):
        ramp = [dm.fc_exposure(s)[0] for s in (-3.5, -2.0, 0.5, 2.0, 3.5)]
        self.assertEqual(ramp, sorted(ramp))

    def test_it_follows_the_exposure_control(self):
        """A stop of exposure has to move the reading by exactly a stop."""
        base = grey_card(5600, 0, 5600, 0)[1]
        for stops in (-2.0, -1.0, 1.0, 2.0):
            code = dm.encode1(0.18, SLOG3)
            out = dm.develop([code] * 3, SG3C, SLOG3, shot=(5600, 0, 800), ei=800 * 2 ** stops)
            got = dm.mul(dm.MATS[SG3C][0], [dm.decode1(c, SLOG3) for c in out])[1]
            self.assertAlmostEqual(math.log2(got / base), stops, places=5)

    def test_a_correctly_exposed_grey_card_reads_green(self):
        self.assertEqual(view(grey_card(5600, 0, 5600, 0), 1, 5600, 0), GREEN)


class WhiteBalanceViews(unittest.TestCase):
    def test_a_neutral_surface_keeps_no_colour_at_all(self):
        """Inside the tolerance the pixel is left in monochrome. Painting a colour on
        everything is what made the view unreadable: you could not tell which parts of
        the picture were already neutral, because neutral looked like a flat patch too."""
        for k, t in ((5600, 0), (3200, 0), (8000, 12), (4300, -20)):
            for mode in (2, 3):
                got = view(grey_card(k, t, k, t), mode, k, t)
                self.assertAlmostEqual(got[0], got[1], places=9,
                                       msg='at %dK tint %+d, mode %d' % (k, t, mode))
                self.assertAlmostEqual(got[1], got[2], places=9)

    def test_the_tolerance_edge_is_a_step_not_a_fade(self):
        """So you can see exactly where neutral ends instead of judging a gradient."""
        inside = view(grey_card(5600, 0, 5650, 0), 2, 5650, 0)
        outside = view(grey_card(5600, 0, 5750, 0), 2, 5750, 0)
        self.assertAlmostEqual(inside[0], inside[2], places=9, msg='dentro deve restare grigio')
        self.assertGreater(abs(outside[0] - outside[2]), 0.3, 'fuori deve saltare nel colore')

    def test_the_readout_is_how_far_the_slider_is_out(self):
        """The number behind a band is in Kelvin and in tint units, not in some
        arbitrary distance: this is what makes the view usable rather than pretty."""
        for shot_k, shot_t in ((5600, 0), (3200, 0), (8000, 10)):
            for dk in (-200, -100, 100, 200):
                got, _ = readout(2, shot_k, shot_t, shot_k - dk, shot_t)
                self.assertAlmostEqual(got / dk, 1.0, delta=0.25,
                                       msg='%dK out at %dK read as %.0f' % (dk, shot_k, got))
            for dt in (-15, -5, 5, 15):
                _, got = readout(3, shot_k, shot_t, shot_k, shot_t - dt)
                self.assertAlmostEqual(got / dt, 1.0, delta=0.15,
                                       msg='%d tint out at %dK read as %.1f' % (dt, shot_k, got))

    def test_the_two_axes_barely_bleed_into_each_other(self):
        """A pure tint error must not show up as Kelvin, or you chase your tail."""
        for shot_k in (3200, 5600, 8000):
            k_bleed, tint = readout(2, shot_k, 0, shot_k, -20)
            self.assertAlmostEqual(tint, 20.0, delta=1.0)
            self.assertLess(abs(k_bleed), 40.0, 'tint bled %.0f K at %dK' % (k_bleed, shot_k))
            kelvin, t_bleed = readout(2, shot_k, 0, shot_k - 200, 0)
            self.assertAlmostEqual(kelvin, 200.0, delta=50.0)
            self.assertLess(abs(t_bleed), 1.5, 'Kelvin bled %.2f tint at %dK' % (t_bleed, shot_k))

    def test_the_cast_shown_is_the_cast_that_is_there(self):
        """Too little Kelvin leaves the picture blue, so the band must be blue."""
        cool = view(grey_card(5600, 0, 5000, 0), 2, 5000, 0)
        warm = view(grey_card(5600, 0, 6400, 0), 2, 6400, 0)
        self.assertGreater(cool[2], cool[0], 'a cool cast must read blue')
        self.assertGreater(warm[0], warm[2], 'a warm cast must read warm')
        green = view(grey_card(5600, 0, 5600, -12), 3, 5600, -12)
        magenta = view(grey_card(5600, 0, 5600, 12), 3, 5600, 12)
        self.assertGreater(green[1], green[0], 'a green cast must read green')
        self.assertGreater(magenta[0], magenta[1], 'a magenta cast must read magenta')

    def test_the_bands_widen_in_steps(self):
        """Measured on the warm side. Below 5600 K the Kelvin scale is so much denser
        that the same distance in uv reads as fewer Kelvin, so a cool error saturates
        at the middle band however far you push it - a property of the scale, not of
        the view."""
        seen = []
        for shot in (5600, 5750, 6400, 8000):
            c = view(grey_card(shot, 0, 5600, 0), 2, 5600, 0)
            if c not in seen:
                seen.append(c)
        self.assertEqual(len(seen), 4, 'the four temperature bands must be distinguishable')

    def test_an_objects_own_colour_is_not_read_as_a_cast(self):
        """This is what makes the view usable on a real scene. A red jumper or a blue
        sky sits thousands of Kelvin from neutral, far past any white balance error, so
        it is the colour of the thing and not a cast: it stays monochrome and keeps out
        of the way. Correctly balanced, the picture comes out essentially grey."""
        for name, rgb in (('cielo', (0.06, 0.12, 0.30)), ('rosso', (0.30, 0.05, 0.04)),
                          ('incarnato', (0.29, 0.20, 0.155))):
            for mode in (2, 3):
                got = view(list(rgb), mode, 5600, 0)
                self.assertAlmostEqual(got[0], got[1], places=9, msg='%s, vista %d' % (name, mode))
                self.assertAlmostEqual(got[1], got[2], places=9)

    def test_a_real_white_balance_error_still_lights_up(self):
        """The gate must not swallow the thing the view exists to show."""
        for err in (150, 400, 1200):
            got = view(grey_card(5600, 0, 5600 - err, 0), 2, 5600 - err, 0)
            self.assertGreater(abs(got[0] - got[2]), 0.2, 'errore di %+d K non segnalato' % err)

    def test_pixels_that_cannot_be_judged_are_marked_not_guessed(self):
        for mode in (2, 3):
            self.assertEqual(view(grey_card(5600, 0, 4000, 0, stops=+6.0), mode, 4000, 0), RED,
                             'clipped: the hue means nothing there')
            self.assertEqual(view(grey_card(5600, 0, 4000, 0, stops=-5.0), mode, 4000, 0), DARK,
                             'too dark to read a cast')

    def test_a_black_pixel_does_not_divide_by_zero(self):
        for mode in (1, 2, 3):
            self.assertEqual(len(view([0.0, 0.0, 0.0], mode, 5600, 0)), 3)


class Emission(unittest.TestCase):
    """The bands have to come out the same colour whatever the timeline works in."""

    def test_the_same_band_survives_every_output_encoding(self):
        for band in (GREEN, PINK, RED, WHITE, DARK):
            ref = None
            for space, gamma in ((SG3C, SLOG3), (DWG, 0), (ACESCCT, 10), (1, 5), (2, 3)):
                emitted = dm.fc_emit(band, space, gamma, space, gamma)
                back = dm.mul(dm.MATS[1][1], dm.mul(dm.MATS[space][0],
                                                    [dm.decode1(c, gamma) for c in emitted]))
                display = [dm.encode1(max(c, 0.0), 2) for c in back]
                if ref is None:
                    ref = display
                for a, b in zip(ref, display):
                    self.assertAlmostEqual(a, b, places=5,
                                           msg='band %s shifted in space %d gamma %d' % (band, space, gamma))
            for a, b in zip(ref, band):
                self.assertAlmostEqual(a, b, places=5, msg='band %s did not survive the round trip' % band)


class PluginWiring(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'SLogMetaRaw.cpp'), encoding='utf-8') as fh:
            self.src = fh.read()

    def test_each_toggle_sits_next_to_the_slider_it_serves(self):
        """OpenFX has no way to put a control on the same row as another, so the only
        thing that ties a toggle to its slider is being declared right before it."""
        panel = self.src[self.src.index('void SLogMetaRawFactory::describeInContext'):]
        for toggle, slider in (('fcTemperature', 'colorTemp'), ('fcTint', 'tint'),
                               ('fcExposure', 'exposure')):
            i = panel.index('defineToggle(p_Desc, page, "%s"' % toggle)
            j = panel.index('defineSlider(p_Desc, page, "%s"' % slider)
            self.assertLess(i, j, '%s must be declared before %s' % (toggle, slider))
            self.assertLess(j - i, 700, '%s drifted away from %s' % (toggle, slider))

    def test_only_one_view_can_be_on(self):
        self.assertIn('toggles[i]->setValue(false)', self.src)

    def test_the_icons_are_shipped_and_referenced(self):
        icons = set(re.findall(r'"(fc_\w+\.png)"', self.src))
        self.assertEqual(icons, {'fc_exposure.png', 'fc_temperature.png', 'fc_tint.png'})
        with open(os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'Makefile'), encoding='utf-8') as fh:
            makefile = fh.read()
        for icon in icons:
            path = os.path.join(ROOT, 'ofx', 'SLogMetaRaw', icon)
            self.assertTrue(os.path.exists(path), '%s is referenced but not in the repo' % icon)
            with open(path, 'rb') as fh:
                self.assertEqual(fh.read(8), b'\x89PNG\r\n\x1a\n', '%s is not a PNG' % icon)
            self.assertIn(icon, makefile, '%s is never copied into the bundle' % icon)

    def test_a_measuring_view_is_never_skipped_as_neutral(self):
        body = self.src[self.src.index('bool SLogMetaRaw::isIdentity'):]
        self.assertIn('p.fcMode == 0', body[:body.index('\n}')])


if __name__ == '__main__':
    unittest.main()
