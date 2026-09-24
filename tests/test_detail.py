# SPDX-License-Identifier: GPL-3.0-or-later
"""The Detail node: its reference model (tests/model/detail.py) and the CPU pipeline against it.

Small images stand in for full frames: `href` makes the radii those of a 1080-line frame and a
small `base` forces a reduced working grid, so every path of the plugin is exercised quickly."""
import math
import os
import random
import struct
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import develop_model as dm  # noqa: E402
from model import detail as D  # noqa: E402
from model import tone as T  # noqa: E402
from plugin_build import test_bin  # noqa: E402

SPACE, GAMMA = 8, 9          # S-Gamut3.Cine / S-Log3
W, H, HREF, BASE = 96, 54, 1080, 20


def scene(w=W, h=H, seed=3):
    """Encoded pixels: a sky gradient, a dark wall, a bright window, texture and a coloured patch."""
    rnd = random.Random(seed)
    img = []
    for y in range(h):
        for x in range(w):
            ev = -3.0 + 5.0 * x / w if y < h // 2 else -4.5
            if w * 0.6 < x < w * 0.8 and h * 0.55 < y < h * 0.85:
                ev = 4.0                                        # a window 8.5 stops over the wall
            ev += 0.12 * math.sin(x * 1.7) * math.cos(y * 1.3) + rnd.gauss(0.0, 0.02)
            tint = (1.0, 0.9, 0.75) if x < w // 3 else (0.7, 0.85, 1.0)
            img.append([dm.encode1(0.18 * 2 ** ev * c, GAMMA) for c in tint])
    return img


def ev_of(px):
    lin = [dm.decode1(c, GAMMA) for c in px]
    return math.log2(max(T.t5_norm(dm.mul(dm.MATS[2][1], dm.mul(dm.MATS[SPACE][0], lin))), 1e-12) / 0.18)


def model(img, controls, w=W, h=H, href=HREF, base=BASE):
    p = D.prepare(w, h, controls, space=SPACE, base=base, href=href)
    return D.render(img, w, h, p, GAMMA)


CASES = [{}, {'localHighlights': -100}, {'localShadows': 100, 'localContrast': -60},
         {'localHighlights': 60, 'localShadows': -40, 'localContrast': 40, 'preserveDetail': 60},
         {'clarity': 80}, {'clarity': -70, 'clarityCenter': 1.5}, {'texture': 90}, {'texture': -90, 'noiseThreshold': 0},
         {'dehaze': 70, 'hazeWarmth': 40, 'hazeLevel': 1.0}, {'dehaze': -50},
         {'localZoneLightExp': -2, 'localZoneShadowExp': 1.5, 'localZonePivot': 1, 'localZoneSpecularFalloff': 0.5},
         {'localHighlights': -80, 'viewGain': 1}, {'viewBase': 1, 'detailRadius': 8, 'edgeThreshold': 0.25},
         {'texture': 50, 'clarity': 50, 'localShadows': 50, 'dehaze': 30},
         {'localHighlights': 60, 'localContrast': 30}, {'localHighlights': -100, 'localWhite': 4.5, 'texture': 40},
         {'localHighlights': -50, 'noiseThreshold': 0}]


class Model(unittest.TestCase):
    """Invariants of the reference (spec_detail.md L1-L10), on the model alone."""

    def test_l1_at_rest_the_node_is_the_identity(self):
        img = scene()
        out, planes = model(img, {})
        self.assertEqual(out, img)
        self.assertEqual(max(abs(g) for g in planes['G']), 0.0)

    def test_l2_on_a_flat_field_the_base_is_the_pointwise_curve(self):
        """No detail to keep: the local tones reduce to the same curve the develop node applies."""
        for ev in (-8.0, -4.0, -1.0, 0.0, 2.0, 4.5):
            img = [[dm.encode1(0.18 * 2 ** ev, GAMMA)] * 3] * (32 * 18)
            ctrl = {'localHighlights': -70, 'localShadows': 60, 'localContrast': 30}
            p = D.prepare(32, 18, ctrl, space=SPACE, base=BASE, href=HREF)
            _, planes = D.render(img, 32, 18, p, GAMMA)
            L = planes['L'][0]
            want = T.t5_curve(L, p['curve'])[0]
            if want > 0.0:
                want *= T.t5_ramp((L - D.FLOOR_EV) / D.FLOOR_W)
            want += D.shoulder(L, p['hlE'], p['hlStart'])[0]   # no detail: Local Highlights is its curve
            self.assertAlmostEqual(planes['G'][200], want, places=6, msg='ev %g' % ev)

    def test_l3_texture_and_clarity_commute_with_exposure(self):
        """Their gains read differences of L: +1 stop in, +1 stop out, once the anchors that follow the
        absolute level move with it (the noise floor off, the Clarity centre raised by a stop)."""
        img = scene()
        brighter = [[dm.encode1(dm.decode1(c, GAMMA) * 2.0, GAMMA) for c in px] for px in img]
        for ctrl in ({'texture': 70, 'noiseThreshold': 0}, {'clarity': 70, 'noiseThreshold': 0}):
            _, a = model(img, dict(ctrl, clarityCenter=0))
            _, b = model(brighter, dict(ctrl, clarityCenter=1.0) if 'clarity' in ctrl else ctrl)
            worst = max(abs(x - y) for x, y in zip(a['G'], b['G']))
            self.assertLess(worst, 1e-6, ctrl)

    def test_l10_a_zone_never_moves_back_as_its_slider_goes_on(self):
        img = scene(48, 27)
        prev = None
        for v in range(0, -101, -20):
            _, planes = model(img, {'localHighlights': v}, 48, 27)
            if prev is not None:
                self.assertTrue(all(g <= q + 1e-9 for g, q in zip(planes['G'], prev)), v)
            prev = planes['G']

    def test_l4_the_halo_of_a_strong_recovery_stays_bounded(self):
        """A 3-stop step at full strength: the dark side next to the edge moves by a small share of it."""
        w, h = 96, 54
        img = [[dm.encode1(0.18 * 2 ** (3.0 if x >= w // 2 else 0.0), GAMMA)] * 3 for y in range(h) for x in range(w)]
        out, planes = model(img, {'localHighlights': -100}, w, h)
        row = (h // 2) * w
        far = planes['G'][row + 4]
        near = max(abs(planes['G'][row + x] - far) for x in range(w // 2 - 6, w // 2))
        self.assertLess(near, 0.35 * 3.0 * 0.1 + 1e-9)

    def test_local_highlights_keeps_the_texture_the_main_node_softens(self):
        """On a +4 stop plateau a +-0.1..0.3 stop texture gains contrast locally, while the main node's shoulder,
        pointwise, keeps less than a third of it. That is the difference between the two Highlights."""
        p = D.prepare(64, 64, {'localHighlights': -100})
        main = T.set_tone({'toneHighlights': -100})
        for amp in (0.1, 0.3):
            local = ((4 + amp + D.local_highlights(4 + amp, 4.0, p)) - (4 - amp + D.local_highlights(4 - amp, 4.0, p))) / (2 * amp)
            point = ((4 + amp + T.t5_curve(4 + amp, main)[0]) - (4 - amp + T.t5_curve(4 - amp, main)[0])) / (2 * amp)
            self.assertGreater(local, 1.1, amp)
            self.assertLess(point, 0.3, amp)

    def test_local_highlights_never_inverts_the_detail(self):
        """Over a fixed base, a brighter pixel always comes out brighter, whatever Soglia bordi says."""
        for edge in (0.25, 0.5, 1.0):
            p = D.prepare(64, 64, {'localHighlights': -100, 'edgeThreshold': edge})
            for base in (0.0, 2.0, 4.0, 6.0):
                Ls = [base - 2.0 + 0.002 * i for i in range(2001)]
                o = [L + D.local_highlights(L, base, p) for L in Ls]
                self.assertGreater(min(b - a for a, b in zip(o, o[1:])), 0.0, 'Soglia bordi %g, base %+g' % (edge, base))

    def test_local_highlights_never_brightens_and_follows_its_slider(self):
        for L, B in ((4.3, 4.0), (0.2, -0.3), (1.0, 3.0), (5.0, 2.0)):
            prev = 0.0
            for v in range(-10, -101, -10):
                g = D.local_highlights(L, B, D.prepare(64, 64, {'localHighlights': v}))
                self.assertLessEqual(g, 0.0)
                self.assertLessEqual(g, prev + 1e-12, (L, B, v))
                prev = g

    def test_local_highlights_halos_stay_within_2_0_0(self):
        """A 3-stop step: the band along the bright side is no wider than 2.0.0's, the dark side moves < 0.1 stop."""
        w, h = 96, 54
        img = [[dm.encode1(0.18 * 2 ** (3.0 if x >= w // 2 else 0.0), GAMMA)] * 3 for y in range(h) for x in range(w)]
        _, planes = model(img, {'localHighlights': -100}, w, h)
        row = (h // 2) * w
        G = planes['G'][row:row + w]
        self.assertLess(max(abs(g - G[4]) for g in G[w // 2 - 6:w // 2]), 0.1)
        self.assertLess(max(abs(g - G[w - 5]) for g in G[w // 2:w // 2 + 6]), 0.5)

    def test_local_highlights_takes_a_clipped_plateau_towards_white(self):
        """The sensor clip is cream-coloured: pulled 3.5 stops down it must not become a cream plate. The same path
        to white as the main node lowers its chroma, at its own hue."""
        w, h = 48, 27
        cream = [1.0, 0.93, 0.80]
        img = [[dm.encode1(0.18 * 2 ** 6.0 * c, GAMMA) for c in cream]] * (w * h)
        out, _ = model(img, {'localHighlights': -100}, w, h)
        lin_in = dm.mul(dm.MATS[SPACE][0], [dm.decode1(c, GAMMA) for c in img[300]])
        lin_out = dm.mul(dm.MATS[SPACE][0], [dm.decode1(c, GAMMA) for c in out[300]])
        def uv(xyz):
            d = xyz[0] + 15 * xyz[1] + 3 * xyz[2]
            return 4 * xyz[0] / d - 0.19783, 6 * xyz[1] / d - 0.31221
        (ui, vi), (uo, vo) = uv(lin_in), uv(lin_out)
        self.assertLess(math.hypot(uo, vo), 0.8 * math.hypot(ui, vi))

    def test_n1_non_finite_pixels_are_copied_and_do_not_spread(self):
        img = scene(48, 27)
        img[5 * 48 + 7] = [float('nan'), 0.4, 0.4]
        img[9 * 48 + 30] = [float('inf')] * 3
        out, planes = model(img, {'localShadows': 80, 'texture': 60}, 48, 27)
        self.assertTrue(math.isnan(out[5 * 48 + 7][0]))
        self.assertEqual(out[9 * 48 + 30], img[9 * 48 + 30])
        self.assertTrue(all(math.isfinite(c) for i, px in enumerate(out) if i not in (5 * 48 + 7, 9 * 48 + 30)
                            for c in px))

    def test_dehaze_leaves_everything_above_the_veil_alone(self):
        img = [[dm.encode1(0.18 * 2 ** ev, GAMMA)] * 3 for ev in [3.0 + 0.01 * i for i in range(32 * 18)]]
        out, _ = model(img, {'dehaze': 100, 'hazeLevel': 2.0}, 32, 18)
        worst = max(abs(ev_of(a) - ev_of(b)) for a, b in zip(img, out))
        self.assertLess(worst, 1e-6)


class CpuParity(unittest.TestCase):
    """src/detail/DetailPasses.cpp against the model: planes within 2e-4 EV, pixels within 5e-4."""

    @classmethod
    def setUpClass(cls):
        cls.exe = test_bin('detail_test')
        if not cls.exe:
            raise unittest.SkipTest('binari di test non compilabili qui')

    def run_cpu(self, img, controls, w=W, h=H, href=HREF, base=BASE, threads=1):
        head = '%d %d %r %d %d %d 1.0 %d\n' % (w, h, float(href), base, SPACE, GAMMA, threads)
        ctrl = ' '.join('%s=%r' % (k, float(v)) for k, v in controls.items()) + '\n'
        body = '\n'.join(' '.join(repr(c) for c in px) for px in img) + '\n'
        out = subprocess.run([self.exe], input=head + ctrl + body, capture_output=True, text=True, check=True).stdout
        return [[float(v) for v in line.split()] for line in out.splitlines()]

    def test_every_control_matches_the_model(self):
        img = scene()
        for ctrl in CASES:
            got = self.run_cpu(img, ctrl)
            out, planes = model(img, ctrl)
            self.assertEqual(len(got), len(out))
            for name, col in (('L', 3), ('B', 4), ('Dg', 5), ('G', 6)):
                # L and B are log2 luminance: near black float32 cancellation (Dehaze removing the veil) shows
                # up in EV while the light differs by nothing, so there they are compared like the pixels below
                visible = (lambda a, b: abs(0.18 * (2 ** a - 2 ** b)) > 2e-6) if name in 'LB' else (lambda a, b: True)
                worst = max([abs(g[col] - m) for g, m in zip(got, planes[name]) if visible(g[col], m)] or [0.0])
                self.assertLess(worst, 2e-4, '%s: piano %s scarto %g' % (ctrl, name, worst))
            worst = 0.0
            for g, m in zip(got, out):
                for a, b in zip(g[:3], m):
                    if abs(dm.decode1(a, GAMMA) - dm.decode1(b, GAMMA)) > 2e-6:
                        worst = max(worst, abs(a - b))
            self.assertLess(worst, 5e-4, '%s: uscita scarto %g' % (ctrl, worst))

    def test_at_rest_the_output_is_the_input_bit_for_bit(self):
        img = scene()
        got = self.run_cpu(img, {})
        f32 = lambda v: struct.unpack('f', struct.pack('f', v))[0]   # the plugin works in float32
        for g, px in zip(got, img):
            self.assertEqual([f32(v) for v in g[:3]], [f32(c) for c in px])   # %.9g round-trips a float32

    def test_l6_one_thread_and_many_give_the_same_bits(self):
        img = scene()
        ctrl = {'texture': 50, 'clarity': 50, 'localShadows': 50, 'dehaze': 30}
        self.assertEqual(self.run_cpu(img, ctrl, threads=1), self.run_cpu(img, ctrl, threads=5))

    def test_full_size_grid_and_reduced_grid(self):
        """s = 1 (base large) and s = 4 (base tiny) both follow the model."""
        img = scene(64, 36)
        for base in (4000, 9):
            got = self.run_cpu(img, {'localHighlights': -60, 'clarity': 40}, 64, 36, base=base)
            _, planes = model(img, {'localHighlights': -60, 'clarity': 40}, 64, 36, base=base)
            worst = max(abs(g[6] - m) for g, m in zip(got, planes['G']))
            self.assertLess(worst, 2e-4, 'base %d' % base)


if __name__ == '__main__':
    unittest.main()
