# SPDX-License-Identifier: GPL-3.0-or-later
"""The false colours: what each view shows, and whether it tells the truth.

The exposure view follows the ARRI ALEXA convention (green on 18% grey, pink one stop over it,
yellow approaching clip, red clipped, blue and purple at the bottom). The two white-balance views
behave like CineMatch's: the picture in grey, casts in orange/blue or green/magenta, near-neutral
casts boosted so they show; the axis comes from the sliders' own response.
"""
import math
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import develop_model as dm
import plugin_build   # noqa: E402

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


def colourfulness(c):
    return max(c) - min(c)


class WhiteBalanceViews(unittest.TestCase):
    def test_a_neutral_surface_stays_grey(self):
        """Grey is the target: move the slider until what should be neutral has no colour left."""
        for k, t in ((5600, 0), (3200, 0), (8000, 12), (4300, -20)):
            for mode in (2, 3):
                got = view(grey_card(k, t, k, t), mode, k, t)
                self.assertLess(colourfulness(got), 1e-3, 'at %dK tint %+d, mode %d' % (k, t, mode))

    def test_the_readout_follows_the_sliders(self):
        """The axis is the sliders' own response: a Kelvin error reads as Kelvin, a tint error as tint."""
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
        """Too little Kelvin leaves the picture blue, so it reads blue; warm reads orange."""
        cool = view(grey_card(5600, 0, 5000, 0), 2, 5000, 0)
        warm = view(grey_card(5600, 0, 6400, 0), 2, 6400, 0)
        self.assertGreater(cool[2], cool[0], 'a cool cast must read blue')
        self.assertGreater(warm[0], warm[2], 'a warm cast must read orange')
        green = view(grey_card(5600, 0, 5600, -12), 3, 5600, -12)
        magenta = view(grey_card(5600, 0, 5600, 12), 3, 5600, 12)
        self.assertGreater(green[1], green[0], 'a green cast must read green')
        self.assertGreater(magenta[0], magenta[1], 'a magenta cast must read magenta')

    def test_near_neutral_casts_are_amplified_up_to_8x(self):
        """CineMatch's saturate(v, remap(s, 0, 1, 8, 1)): the display saturation of the pixel, times 8 near
        neutral and 1 at full colour, so a small error is seen before it is a visible cast."""
        for err in (50, 100, 200, 800):
            xyz = grey_card(5600, 0, 5600 - err, 0)
            got = view(xyz, 2, 5600 - err, 0)
            rgb = [max(c, 0.0) for c in dm.mul(dm.MATS[1][1], xyz)]
            lo = (min(rgb) / max(rgb)) ** (1 / 2.2)
            r = (1 - lo) / (1 + lo)
            light = (max(got) + min(got)) / 2
            shown = colourfulness(got) / (2 * min(light, 1 - light))
            self.assertAlmostEqual(shown, r * (8 - 7 * r), places=4, msg='%d K' % err)
        self.assertGreater(colourfulness(view(grey_card(5600, 0, 5300, 0), 2, 5300, 0)), 0.15)

    def test_a_larger_cast_reads_stronger(self):
        seen = [colourfulness(view(grey_card(5600 + err, 0, 5600, 0), 2, 5600, 0)) for err in (50, 150, 400, 1200)]
        self.assertEqual(seen, sorted(seen))
        self.assertGreater(seen[-1], seen[0])

    def test_each_view_lights_only_its_own_axis(self):
        """A green cast leaves the temperature view grey and a warm one leaves the tint view grey,
        so each view answers only to its slider."""
        green = view(grey_card(5600, 0, 5600, -15), 2, 5600, -15)
        warm = view(grey_card(5600, 0, 6600, 0), 3, 6600, 0)
        self.assertLess(colourfulness(green), 1e-6)
        self.assertLess(colourfulness(warm), 1e-6)

    def test_pixels_too_dark_or_too_bright_fade_to_grey(self):
        """There the hue is noise or clipping, not a cast: it is not guessed."""
        for mode in (2, 3):
            for stops in (-7.0, 6.0):
                got = view(grey_card(5600, 0, 4000, 0, stops=stops), mode, 4000, 0)
                self.assertLess(colourfulness(got), 1e-6, 'mode %d at %+g stops' % (mode, stops))

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
        self.src = plugin_build.source()

    def test_each_toggle_sits_next_to_the_slider_it_serves(self):
        """OpenFX has no way to put a control on the same row as another, so the only
        thing that ties a toggle to its slider is being declared right before it."""
        panel = plugin_build.body(self.src, 'void DevelopFactory::describeInContext')
        for toggle, slider in (('fcTemperature', 'colorTemp'), ('fcTint', 'tint'),
                               ('fcExposure', 'exposure')):   # fcZones heads its own group
            i = panel.index('defineToggle(d, page, "%s"' % toggle)
            j = panel.index('defineSlider(d, page, "%s"' % slider)
            self.assertLess(i, j, '%s must be declared before %s' % (toggle, slider))
            self.assertLess(j - i, 700, '%s drifted away from %s' % (toggle, slider))

    def test_only_one_view_can_be_on(self):
        self.assertIn('toggles[i]->setValue(false)', self.src)

    def test_the_icons_are_shipped_and_referenced(self):
        icons = set(re.findall(r'"((?:fc|view)_\w+\.png)"', self.src))
        self.assertEqual(icons, {'fc_exposure.png', 'fc_temperature.png', 'fc_tint.png', 'fc_zones.png',
                                 'view_gain.png', 'view_base.png'})
        with open(os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'Makefile'), encoding='utf-8') as fh:
            makefile = fh.read()
        for icon in icons:
            path = os.path.join(ROOT, 'ofx', 'SLogMetaRaw', icon)
            self.assertTrue(os.path.exists(path), '%s is referenced but not in the repo' % icon)
            with open(path, 'rb') as fh:
                self.assertEqual(fh.read(8), b'\x89PNG\r\n\x1a\n', '%s is not a PNG' % icon)
            self.assertIn(icon, makefile, '%s is never copied into the bundle' % icon)

    def test_a_measuring_view_is_never_skipped_as_neutral(self):
        self.assertIn('p.fcMode == 0', plugin_build.body(self.src, 'bool DevelopEffect::isIdentity'))


if __name__ == '__main__':
    unittest.main()
