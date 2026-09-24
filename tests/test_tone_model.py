# SPDX-License-Identifier: GPL-3.0-or-later
"""The v5 tone engine on its Python reference, tests/model/{tone,color}.py.

The model is the truth the C++ and Metal ports are measured against, so these
tests pin its properties (spec_tone.md par. 8.3: I1-I9, I13, I14), its numbers
(the anchors of par. 8.1 and 8.4, from the prototype tone_v5f.py) and what a
1D LUT can carry of it. SLOW=1 adds the 5^5 slider grid, the Zone grid and a
random sweep.
"""
import itertools
import math
import os
import random
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import develop_model as dm  # noqa: E402
from model import tone as T  # noqa: E402

SLOW = bool(os.environ.get('SLOW'))
GREY = T.SM_T5_GREY
DWG, REC709, REC2020, P3D65, SG3, SG3C = 0, 1, 2, 3, 7, 8
SRGB, SLOG3 = 6, 9
EGRID = [-16.0 + 0.05 * i for i in range(561)]
FINE = [-16.0 + 0.01 * i for i in range(2801)]
SLIDERS = ('toneContrast', 'toneHighlights', 'toneShadows', 'toneWhites', 'toneBlacks')
PATCH = {'skin': (194, 150, 130), 'sky': (98, 122, 157), 'foliage': (87, 108, 67), 'red': (175, 54, 60)}
PATCH_EV = {'skin': 1.0, 'sky': 3.0, 'foliage': -1.0, 'red': 0.0}


def shift(e, p):
    """Stops a neutral at e stops from grey is moved by."""
    return T.t5_gain(GREY * 2.0 ** e, p)[0]


def slope(e, p, h=1e-5):
    return 1.0 + (shift(e + h, p) - shift(e - h, p)) / (2.0 * h)


def secants(p, grid):
    s = [shift(e, p) for e in grid]
    return [1.0 + (s[i + 1] - s[i]) / (grid[i + 1] - grid[i]) for i in range(len(grid) - 1)]


def gain_at_black(p):
    return 2.0 ** T.t5_gain(0.0, p)[0]


def zone(name, exp=0.0, rng=None, falloff=None, sat=0.0):
    c = {'zone%sExp' % name: exp, 'zone%sSat' % name: sat}
    if rng is not None:
        c['zone%sRange' % name] = rng
    if falloff is not None:
        c['zone%sFalloff' % name] = falloff
    return c


def upvp(xyz):
    d = xyz[0] + 15.0 * xyz[1] + 3.0 * xyz[2]
    return 4.0 * xyz[0] / d, 9.0 * xyz[1] / d


def chroma(xyz):
    u, v = upvp(xyz)
    return math.hypot(u - T.SM_T5_UW, v - T.SM_T5_VW)


def patch_xyz(name, ev):
    """A Macbeth patch (sRGB 8 bit) scaled so its Rec.2020 norm sits at ev stops from grey."""
    xyz = dm.mul(dm.MATS[REC709][0], [dm.decode1(v / 255.0, SRGB) for v in PATCH[name]])
    k = GREY * 2.0 ** ev / T.t5_norm(dm.mul(dm.MATS[REC2020][1], xyz))
    return [c * k for c in xyz]


def random_controls(rnd, colour=True):
    c = {n: rnd.uniform(-100, 100) for n in SLIDERS}
    c['zonePivot'] = rnd.uniform(-3, 3)
    for z in T.ZONES:
        c.update(zone(z, rnd.uniform(-6, 6), rnd.uniform(-8, 8), rnd.uniform(0.5, 6),
                      rnd.uniform(-100, 100) if colour else 0.0))
    if colour:
        c['toneSaturation'], c['toneVibrance'] = rnd.uniform(-100, 100), rnd.uniform(-100, 100)
        c['softClip'], c['softClipLevel'] = rnd.random() < 0.5, rnd.uniform(1, 10)
        c['softClipColor'] = rnd.uniform(-100, 100)
    return c


def giveback(make, values, grid, sign=None):
    """Largest amount any tone moves back while the control keeps moving one way."""
    ps = [T.set_tone(make(v)) for v in values]
    worst = 0.0
    for e in grid:
        sg = sign(e) if sign else math.copysign(1.0, values[-1])
        best = -math.inf
        for p in ps:
            s = sg * shift(e, p)
            worst = max(worst, best - s)
            best = max(best, s)
    return worst


# spec_tone par. 8.1: shift at -10, -6, -4, -2, 0, +1, +2, +3, +4, +5.5 stops; gain at black; slope min, max.
# The Highlights rows are the shoulder: Bianco 2.5, shot EI, so -100 lands +6 on +2.5
ANCHORS = (
    ('Contrast -100', {'toneContrast': -100},
     (1.9732, 1.8103, 1.5232, 0.9242, 0, -0.4898, -0.9242, -1.2703, -1.5232, -1.7597), 3.9963, 0.5, 0.9996),
    ('Contrast +100', {'toneContrast': 100},
     (-3.9465, -3.6206, -3.0464, -1.8485, 0, 0.9797, 1.8485, 2.5406, 3.0464, 3.5193), 0.062616, 1.0009, 2),
    ('Highlights -20', {'toneHighlights': -20},
     (0, 0, 0, 0, 0, -0.0153, -0.1058, -0.2724, -0.4866, -0.8527), 1, 0.7393, 1),
    ('Highlights -50', {'toneHighlights': -50},
     (0, 0, 0, 0, 0, -0.0342, -0.2362, -0.608, -1.0861, -1.9034), 1, 0.4182, 1),
    ('Highlights -100', {'toneHighlights': -100},
     (0, 0, 0, 0, 0, -0.0548, -0.3779, -0.9729, -1.7378, -3.0455), 1, 0.0691, 1),
    ('Highlights +100', {'toneHighlights': 100},
     (0, 0, 0, 0, 0, 0.0294, 0.203, 0.5225, 0.9333, 1.6356), 1, 1, 1.5),
    ('Shadows -100', {'toneShadows': -100},
     (-2, -2, -2, -0.75, 0, 0, 0, 0, 0, 0), 0.25, 1, 2),
    ('Shadows +50', {'toneShadows': 50},
     (1, 1, 1, 0.4875, 0, 0, 0, 0, 0, 0), 2, 0.35, 1),
    ('Shadows +100', {'toneShadows': 100},
     (2, 2, 1.7839, 0.4875, 0, 0, 0, 0, 0, 0), 4, 0.35, 1),
    ('Whites -100', {'toneWhites': -100},
     (0, 0, 0, 0, 0, 0, 0, 0, -0.2438, -1), 1, 0.35, 1),
    ('Whites +100', {'toneWhites': 100},
     (0, 0, 0, 0, 0, 0, 0, 0, 0.375, 1), 1, 1, 2),
    ('Blacks -5', {'toneBlacks': -5},
     (-0.1431, -0.1122, -0.0585, -0.0135, 0, 0, -0.0011, -0.0006, -0.0003, -0.0001), 0.90404, 0.9981, 1.0309),
    ('Blacks -50', {'toneBlacks': -50},
     (-1.4303, -0.9959, -0.4434, -0.0921, 0, 0.0001, -0.0073, -0.0036, -0.0018, -0.0006), 0.36084, 0.9876, 1.2915),
    ('Blacks -100', {'toneBlacks': -100},
     (-2.8117, -1.643, -0.6457, -0.1271, 0, 0.0001, -0.0099, -0.0049, -0.0025, -0.0009), 0.12851, 0.9831, 1.5261),
    ('Blacks +100', {'toneBlacks': 100},
     (0.9444, 0.7931, 0.474, 0.1255, 0, 0.0002, 0.0112, 0.0056, 0.0028, 0.001), 1.9394, 0.7909, 1.0187),
    ('Black -3', {'zoneBlackExp': -3},
     (-3, -3, 0, 0, 0, 0, 0, 0, 0, 0), 0.125, 1, 2.8571),
    ('Black +3', {'zoneBlackExp': 3},
     (3, 1.2187, 0, 0, 0, 0, 0, 0, 0, 0), 8, 0.35, 1),
    ('Shadow -1', {'zoneShadowExp': -1},
     (-1, -1, -1, -1, -0.5, 0, 0, 0, 0, 0), 0.5, 1, 1.6667),
    ('Light -1', {'zoneLightExp': -1},
     (0, 0, 0, 0, -0.4875, -0.9998, -1, -1, -1, -1), 1, 0.35, 1),
    ('Light -3', {'zoneLightExp': -3},
     (0, 0, 0, 0, -0.4875, -1.1375, -1.7875, -2.4375, -2.9443, -3), 1, 0.35, 1),
    ('Light +3', {'zoneLightExp': 3},
     (0, 0, 0, 0, 1.3929, 2.9863, 3, 3, 3, 3), 1, 1, 2.8571),
    ('Specular -3', {'zoneSpecularExp': -3},
     (0, 0, 0, 0, 0, 0, 0, 0, 0, -0.8938), 1, 0.35, 1),
    ('Specular +3', {'zoneSpecularExp': 3},
     (0, 0, 0, 0, 0, 0, 0, 0, 0, 2.5534), 1, 1, 2.8571),
    ('Soft Clip 2.5', {'softClip': 1, 'softClipLevel': 2.5},
     (0.0026, 0.0026, 0.0026, 0.0026, 0, -0.0181, -0.1429, -0.6429, -1.5181, -2.9983), 1.0018, 0, 1),
    ('C+30 H-60 S+40', {'toneContrast': 30, 'toneHighlights': -60, 'toneShadows': 40},
     (-0.1122, -0.0369, 0.0958, -0.018, 0, 0.1554, -0.0138, -0.4353, -0.9948, -1.9398), 0.91767, 0.324, 1.2311),
    ('C+100 H-100', {'toneContrast': 100, 'toneHighlights': -100},
     (-3.9465, -3.6206, -3.0464, -1.8485, 0, 0.6081, 0.2187, -0.5715, -1.4598, -2.8358), 0.062616, 0.0606, 2),
)
ANCHOR_EV = (-10, -6, -4, -2, 0, 1, 2, 3, 4, 5.5)

# spec_tone par. 8.4: chroma u'v' out/in for skin +1, sky +3, foliage -1, red 0 (Y out/in in brackets there)
COLOUR_ANCHORS = (
    ({'toneSaturation': -100}, (0, 0, 0, 0)),
    ({'toneSaturation': 100}, (2.091, 1.812, 1.997, 1.622)),
    ({'toneVibrance': -100}, (0.447, 0.538, 0.480, 0.760)),
    ({'toneVibrance': 100}, (1.172, 1.417, 1.565, 1.187)),
    (zone('Shadow', sat=-100), (1, 1, 0, 0.484)),
    (zone('Specular', sat=-100), (1, 1, 1, 1)),
    (zone('Light', sat=50), (1.538, 1.426, 1, 1.269)),
    ({'toneHighlights': -100}, (0.995, 0.909, 1, 1)),   # the path to white, in Oklab
    ({'softClip': 1, 'softClipLevel': 2.5}, (0.993, 0.672, 1, 1)),
)


# 65-point S-Log3 LUT: 3.5 CV (spec_tone par. 8.5) holds except here, measured: a 4-8x gain at the
# black code (95) and the Shadow/Black bands in the linear toe, or a narrow expansion at a zone edge
LUT_65_OVER = {
    ('toneContrast', -100): 3.7,
    ('zoneBlackExp', -3.0, 0.5): 5.2, ('zoneBlackExp', -3.0, 1.0): 4.3,
    ('zoneBlackExp', 3.0, 0.5): 18.4, ('zoneBlackExp', 3.0, 1.0): 18.2, ('zoneBlackExp', 3.0, 2.0): 17.7,
    ('zoneShadowExp', -3.0, 0.5): 4.7, ('zoneShadowExp', -3.0, 1.0): 4.1,
    ('zoneShadowExp', 3.0, 0.5): 10.8, ('zoneShadowExp', 3.0, 1.0): 10.8, ('zoneShadowExp', 3.0, 2.0): 10.8,
    ('zoneLightExp', 3.0, 1.0): 3.8,
}


class Primitives(unittest.TestCase):
    def test_the_norm_of_a_neutral_is_its_value(self):
        """norm(x, x, x) = x for any sign and size, and the max|c| guard keeps extremes finite."""
        for x in (1e-20, 0.18, 3.0, 1e20, -0.5):
            self.assertAlmostEqual(T.t5_norm([x, x, x]) / abs(x), 1.0, places=14)
        self.assertEqual(T.t5_norm([0.0, 0.0, 0.0]), 0.0)
        self.assertAlmostEqual(T.t5_norm([1e300, -1e300, 0.0]) / 1e300, 1.0, places=14)
        self.assertAlmostEqual(T.t5_norm([1e-25, 0.0, -1e-26]) / 1e-25, 1.001 / 1.01, places=14)

    def test_the_log_floor_is_minus_16_stops(self):
        """Black reads -16 EV; eight stops above it the floor lifts by 1e-5 stop, at grey by 1.7e-10."""
        self.assertEqual(T.t5_log(0.0), -16.0)
        self.assertAlmostEqual(T.t5_log(GREY * 2.0 ** -8), -8.0, delta=2e-5)
        self.assertAlmostEqual(T.t5_log(GREY), 0.0, delta=2e-10)

    def test_the_ramp_is_c2(self):
        """Value, slope and curvature of the ramp match across its joints."""
        for u0 in (0.0, T.SM_T5_DELTA, 1.0 - T.SM_T5_DELTA, 1.0):
            h = 1e-4
            d1 = [(T.t5_ramp(u0 + s * h + h / 2) - T.t5_ramp(u0 + s * h - h / 2)) / h for s in (-1, 1)]
            d2 = [(T.t5_ramp(u0 + s * h + h) - 2 * T.t5_ramp(u0 + s * h) + T.t5_ramp(u0 + s * h - h)) / h / h
                  for s in (-1.5, 1.5)]
            self.assertLess(abs(d1[0] - d1[1]), 1e-3)
            self.assertLess(abs(d2[0] - d2[1]), 0.05 * T.SM_T5_RMAX / T.SM_T5_DELTA)
        self.assertEqual((T.t5_ramp(0.0), T.t5_ramp(0.5), T.t5_ramp(1.0)), (0.0, 0.5, 1.0))

    def test_h_matches_its_direct_form(self):
        """The tanh form of (1 - e^-x)/x is the function itself, series included."""
        x = 1e-8
        while x < 200.0:
            self.assertAlmostEqual(T.t5_h(x) / (-math.expm1(-x) / x), 1.0, places=12)
            x *= 1.07

    def test_a_zone_moves_exactly_e_past_its_band(self):
        """rho is 0 on the still side and exactly 1 once past the band."""
        self.assertEqual(T.t5_zone(0.5, 1.0, 1.0, 0.5, 0.5), 0.0)
        self.assertEqual(T.t5_zone(1.5, 1.0, -1.0, 0.5, 0.5), 0.0)
        self.assertEqual(T.t5_zone(9.0, 1.0, 1.0, 0.5, 0.5), 1.0)
        self.assertEqual(T.t5_zone(-9.0, -1.0, -1.0, 0.5, 0.5), 1.0)


class Policy(unittest.TestCase):
    def test_the_fields_are_those_of_develop_params(self):
        """set_tone fills exactly the 59 tone scalars of DevelopParams."""
        p = T.set_tone({})
        self.assertEqual(tuple(p), T.TONE_FIELDS)
        self.assertEqual(sum(len(v) if isinstance(v, list) else 1 for v in p.values()), 59)

    def test_at_rest_the_stage_is_off(self):
        """I1: neutral controls turn every stage off, whatever Pivot, Range, Falloff and roof settings say."""
        rest = {'zonePivot': 2.0, 'softClipLevel': 7.0, 'softClipColor': 50.0}
        for z in T.ZONES:
            rest.update({'zone%sRange' % z: 3.0, 'zone%sFalloff' % z: 4.0})
        for c in ({}, rest):
            p = T.set_tone(c)
            self.assertFalse(T.active(p))
            self.assertEqual((p['toneOn'], p['colorOn'], p['roofOn']), (0, 0, 0))
            self.assertEqual(p['zoneE'], [0.0] * 7)

    def test_nominal_zones_are_filled_even_at_rest(self):
        """The Zone false colour and zone Sat read Range and Falloff with every stage off."""
        p = T.set_tone({})
        self.assertEqual(p['zNomEdge'], [-4.0, 1.0, -1.0, 4.0])
        self.assertEqual(p['zNomInvF'], [1.0, 0.5, 0.5, 1.0])

    def test_values_are_clamped_to_the_declared_ranges(self):
        """A value past a range reads as the end of the range."""
        for name, (lo, hi, _d) in T.CONTROLS.items():
            base = {'softClip': 1} if name.startswith('softClip') and name != 'softClip' else {}
            self.assertEqual(T.set_tone(dict(base, **{name: hi + 50})), T.set_tone(dict(base, **{name: hi})), name)
            self.assertEqual(T.set_tone(dict(base, **{name: lo - 50})), T.set_tone(dict(base, **{name: lo})), name)

    def test_unknown_names_are_refused(self):
        """The v4 names and the pre-coherence colour names are not tone controls."""
        for name in ('highlights', 'contrast', 'colorBoost', 'colorRecovery', 'colorVibrance', 'colorSaturation'):
            with self.assertRaises(KeyError):
                T.set_tone({name: 10})

    def test_every_control_lands_in_its_slot(self):
        """Fixed slot map: Specular, Whites, Light up; Black, Shadows, Shadow down. Highlights is the shoulder."""
        want = {'toneWhites': (1, 3.5, 0.5), 'toneShadows': (5, -1.0, 1.0)}
        for name, (slot, edge, E) in want.items():
            p = T.set_tone({name: 50})
            self.assertEqual([i for i in range(7) if p['zoneE'][i]], [slot])
            self.assertEqual((p['zoneEdge'][slot], p['zoneE'][slot]), (edge, E))
            self.assertEqual(p['hlE'], 0.0)
        p = T.set_tone({'toneHighlights': 50})
        self.assertEqual(p['zoneE'], [0.0] * 7)
        self.assertEqual((p['hlE'], p['hlStart']), (0.625 * T.SM_T5_HL_CPLUS, 0.0))
        for z, slot, edge in zip(T.ZONES, T.ZONE_SLOT, T.ZONE_RANGE):
            p = T.set_tone({'zone%sExp' % z: 1.5})
            self.assertEqual([i for i in range(7) if p['zoneE'][i]], [slot])
            self.assertEqual((p['zoneEdge'][slot], p['zoneE'][slot]), (edge, 1.5))

    def test_edges_are_carried_through_contrast(self):
        """With Contrast the stored edge is C(edge) and the shoulder starts at C(0): both stay at their scene stop."""
        p = T.set_tone({'toneContrast': 100, 'toneWhites': -100, 'zonePivot': 0.5})
        self.assertAlmostEqual(p['zoneEdge'][1], 3.5 + 4.0 * math.tanh(3.0 / 4.0), places=15)
        self.assertAlmostEqual(p['zoneFill'][1], 0.25 * (1.0 + 4.0 * (math.tanh(4.0 / 4.0) - math.tanh(3.0 / 4.0))),
                               places=14)
        p = T.set_tone({'toneContrast': 100, 'toneHighlights': -100, 'zonePivot': 0.5})
        self.assertAlmostEqual(p['hlStart'], -4.0 * math.tanh(0.5 / 4.0), places=15)

    def test_the_colour_gamut_follows_the_output_only(self):
        """R is the output gamut when the node converts to Rec.709, Rec.2020 or P3, else Rec.2020."""
        for out in range(11):
            self.assertEqual(T.set_tone({}, out, False)['refSpace'], REC2020)
            self.assertEqual(T.set_tone({}, out, True)['refSpace'], out if 1 <= out <= 5 else REC2020)

    def test_blacks_and_soft_clip_fields(self):
        """Blacks -100 takes 7/8 of the veil and +100 doubles it; the roof sits at grey * 2^(h + renorm)."""
        self.assertAlmostEqual(T.set_tone({'toneBlacks': -100})['blkA'], 0.875, places=15)
        self.assertAlmostEqual(T.set_tone({'toneBlacks': 100})['blkA'], -1.0, places=15)
        p = T.set_tone({'softClip': 1, 'softClipLevel': 3.0, 'softClipColor': 100})
        self.assertEqual((p['roofOn'], p['roofStops'], p['roofPurity']), (1, 3.0, 0.5))
        self.assertAlmostEqual(p['roofLin'], GREY * 2.0 ** (3.0 + p['roofRenorm']), places=15)
        self.assertAlmostEqual(shift(0.0, p), 0.0, delta=1e-9)


class Invariants(unittest.TestCase):
    def test_i1_at_rest_the_output_is_the_input_bit_for_bit(self):
        """I1: with neutral controls tone5 returns the very same XYZ."""
        p = T.set_tone({})
        rnd = random.Random(1)
        for _ in range(200):
            xyz = [rnd.uniform(-0.5, 4.0) for _ in range(3)]
            self.assertEqual(T.tone5(xyz, p), xyz)

    def test_i3_i9_finite_everywhere_and_black_stays_black(self):
        """I3, I9: no NaN or Inf from 1e-12 to 1e6 with negative channels, and black maps to black."""
        rnd = random.Random(3)
        bad = []
        for _ in range(600):
            c = random_controls(rnd)
            p = T.set_tone(c, rnd.choice((REC709, REC2020, P3D65)), True)
            for sp in (DWG, REC709, SG3C):
                for _k in range(10):
                    mag = 10.0 ** rnd.uniform(-12, 6)
                    rgb = [rnd.uniform(-0.3, 1.0) * mag for _ in range(3)]
                    out = dm.mul(dm.MATS[sp][1], T.tone5(dm.mul(dm.MATS[sp][0], rgb), p))
                    if not all(map(math.isfinite, out)):
                        bad.append((c, rgb))
            self.assertEqual(T.tone5([0.0, 0.0, 0.0], p), [0.0, 0.0, 0.0])
        self.assertEqual(bad, [])

    def test_i5_the_curvature_is_continuous(self):
        """I5: jumps of T'' shrink with the sampling step, as they only can if T'' is continuous."""
        hh = 1e-3

        def d2(p, e):
            return (shift(e + hh, p) - 2.0 * shift(e, p) + shift(e - hh, p)) / (hh * hh)

        def jump(p, step):
            n = int(round(22.0 / step))
            v = [d2(p, -12.0 + step * i) for i in range(n + 1)]
            return max(abs(v[i + 1] - v[i]) for i in range(n))

        for c in ({'toneHighlights': -100}, {'toneWhites': 100}, {'toneBlacks': -100},
                  zone('Specular', 3.0, falloff=0.5), {'softClip': 1, 'softClipLevel': 2.5},
                  {'toneContrast': 100, 'toneHighlights': 100, 'toneWhites': 100}):
            p = T.set_tone(c)
            self.assertGreater(jump(p, 0.02) / jump(p, 0.004), 4.0, c)

    def test_i6_the_tone_keeps_chromaticity(self):
        """I6: without the colour stage a pixel only changes brightness (Highlights < 0 heads for white: Colour)."""
        rnd = random.Random(6)
        for _ in range(600):
            c = random_controls(rnd, colour=False)
            c['toneHighlights'] = abs(c['toneHighlights'])
            p = T.set_tone(c)
            xyz = [rnd.uniform(0.01, 2.0) for _ in range(3)]
            a, b = upvp(xyz), upvp(T.tone5(xyz, p))
            self.assertLess(max(abs(a[0] - b[0]), abs(a[1] - b[1])), 1e-14)

    def test_i7_the_node_gamut_does_not_matter(self):
        """I7: the same scene gives the same result in all 11 node gamuts, colour stage and Soft Clip included."""
        rnd = random.Random(7)
        worst = 0.0
        for _ in range(200):
            c = random_controls(rnd)
            c['softClip'] = True
            p = T.set_tone(c, rnd.choice((REC709, REC2020, P3D65)), True)
            xyz = [rnd.uniform(0.01, 2.0) for _ in range(3)]
            outs = [dm.mul(dm.MATS[sp][0], dm.mul(dm.MATS[sp][1], T.tone5(
                dm.mul(dm.MATS[sp][0], dm.mul(dm.MATS[sp][1], xyz)), p))) for sp in range(11)]
            for o in outs[1:]:
                worst = max(worst, max(abs(x - y) / max(1.0, abs(x)) for x, y in zip(outs[0], o)))
        self.assertLess(worst, 1e-12)

    def test_i8_past_its_band_a_zone_is_an_exposure(self):
        """I8: beyond the transition the shift is exactly E, even at Zone +-6."""
        cases = [({'toneWhites': v}, 12.0, v / 100.0) for v in (-100, -50, 50, 100)]
        cases += [({'toneShadows': v}, -13.5, 2.0 * v / 100.0) for v in (-100, -50, 50, 100)]
        cases += [(zone('Specular', E), 4.0 + 1.6 * abs(E) + 2.0, E) for E in (-6, -3, 3, 6)]
        cases += [(zone('Light', E), -1.0 + 1.6 * abs(E) + 3.0, E) for E in (-6, -3, 3, 6)]
        cases += [(zone('Black', E), -4.0 - 1.6 * abs(E) - 2.0, E) for E in (-3, 3)]
        for c, e, E in cases:
            self.assertAlmostEqual(shift(e, T.set_tone(c)), E, places=12, msg=c)
        with_c = T.set_tone(dict(zone('Specular', -3.0), toneContrast=100))
        self.assertAlmostEqual(shift(12.0, with_c) - shift(12.0, T.set_tone({'toneContrast': 100})), -3.0, places=12)

    def test_i13_no_tone_moves_back_while_a_slider_keeps_going(self):
        """I13: sweeping one control one way never gives a tone back (Blacks: at most 0.017 stop)."""
        grid = EGRID[::2]
        steps = [i / 20.0 for i in range(21)]
        for name in ('toneHighlights', 'toneShadows', 'toneWhites'):
            for sg in (-1, 1):
                w = giveback(lambda v, n=name: {n: v}, [sg * 100 * s for s in steps], grid)
                self.assertLess(w, 1e-12, (name, sg))
        for z in T.ZONES:
            for sg in (-1, 1):
                w = giveback(lambda v, z=z: zone(z, v), [sg * 6.0 * s for s in steps], grid)
                self.assertLess(w, 1e-12, (z, sg))
        for sg in (-1, 1):
            w = giveback(lambda v: {'toneContrast': v}, [sg * 100 * s for s in steps], grid,
                         sign=lambda e, sg=sg: sg * (1.0 if e >= 0.0 else -1.0))
            self.assertLess(w, 1e-12, ('toneContrast', sg))
            w = giveback(lambda v: {'toneBlacks': v}, [sg * 100 * s for s in steps], grid)
            self.assertLess(w, 0.018, ('toneBlacks', sg))

    def test_i13_holds_whatever_the_other_controls(self):
        """I13 with every other control random: the proof needs no help from the defaults. It covers the slots;
        Highlights, before them, also moves their edges, so it is monotone on its own only (test_highlights)."""
        rnd = random.Random(13)
        swept = ('toneShadows', 'toneWhites') + tuple('zone%sExp' % z for z in T.ZONES)
        grid = EGRID[::4]
        for _ in range(30):
            base = random_controls(rnd)
            name = rnd.choice(swept)
            top = 6.0 if name.startswith('zone') else 100.0
            sg = rnd.choice((-1, 1))
            w = giveback(lambda v: dict(base, **{name: v}), [sg * top * i / 10.0 for i in range(11)], grid)
            self.assertLess(w, 1e-12, (name, sg, base))

    def test_i14_moving_an_edge_moves_the_output_continuously(self):
        """I14: a 0.001 stop edge move changes the output by at most 0.002 stop, also where edges cross."""
        cases = (({'toneHighlights': -100}, 'Light', 3.0, 1.0, 0.001),
                 ({'toneHighlights': 100}, 'Light', -3.0, 1.0, 0.001),
                 ({'toneWhites': -100}, 'Specular', 3.0, 3.5, 0.001),
                 ({'toneShadows': 100}, 'Shadow', -3.0, -1.0, -0.001),
                 ({'toneShadows': 100}, 'Black', 3.0, -6.0, -0.001))
        for base, z, E, edge, de in cases:
            p = T.set_tone(dict(base, **zone(z, E, edge)))
            q = T.set_tone(dict(base, **zone(z, E, edge + de)))
            self.assertLess(max(abs(shift(e, p) - shift(e, q)) for e in FINE), 0.002, (base, z))

    def test_edges_stay_in_scene_stops_under_contrast(self):
        """With Contrast +-100 the still side of a slot is exactly where Contrast alone puts it."""
        cases = (({'toneContrast': 100, 'toneHighlights': -100}, {'toneContrast': 100}, 0.0, 1),
                 ({'toneContrast': -100, 'toneShadows': 100}, {'toneContrast': -100}, -1.0, -1),
                 (dict(zone('Light', -3.0), toneContrast=100), {'toneContrast': 100}, -1.0, 1),
                 (dict(zone('Light', 3.0), **zone('Shadow', -3.0)), zone('Light', 3.0), 1.0, -1))
        for c, c0, edge, dirn in cases:
            p, q = T.set_tone(c), T.set_tone(c0)
            for d in (0.0, 0.25, 0.5, 1.0, 2.0, 6.0):
                e = edge - dirn * d
                self.assertEqual(shift(e, p), shift(e, q), (c, e))


class Anchors(unittest.TestCase):
    def test_the_spec_table(self):
        """spec_tone par. 8.1: shifts, gain at black and slope range of a neutral, within 1e-3."""
        for label, c, shifts, g0, smin, smax in ANCHORS:
            p = T.set_tone(c)
            for e, want in zip(ANCHOR_EV, shifts):
                self.assertAlmostEqual(shift(e, p), want, delta=1e-3, msg='%s at %+g' % (label, e))
            self.assertAlmostEqual(gain_at_black(p), g0, delta=1e-3, msg=label)
            sl = [slope(e, p) for e in EGRID]
            self.assertAlmostEqual(min(sl), smin, delta=1e-3, msg=label)
            self.assertAlmostEqual(max(sl), smax, delta=1e-3, msg=label)

    def test_the_colour_table(self):
        """spec_tone par. 8.4: chroma ratio on four Macbeth patches, and the Y taken off the sky at +3."""
        for c, want in COLOUR_ANCHORS:
            p = T.set_tone(c)
            for name, w in zip(PATCH, want):
                xi = patch_xyz(name, PATCH_EV[name])
                xo = T.tone5(xi, p)
                self.assertAlmostEqual(chroma(xo) / chroma(xi), w, delta=2e-3, msg=(c, name))
        p = T.set_tone({'toneHighlights': -100})
        self.assertAlmostEqual(T.tone5(patch_xyz('sky', 3.0), p)[1] / patch_xyz('sky', 3.0)[1], 0.510, delta=1e-3)
        p = T.set_tone({'softClip': 1, 'softClipLevel': 2.5})
        self.assertAlmostEqual(T.tone5(patch_xyz('sky', 3.0), p)[1] / patch_xyz('sky', 3.0)[1], 0.640, delta=1e-3)


class Grids(unittest.TestCase):
    def check(self, controls, grid, smin, smax, grey=False):
        worst = [math.inf, -math.inf]
        for c in controls:
            p = T.set_tone(c)
            s = secants(p, grid)
            self.assertTrue(all(map(math.isfinite, s)), c)
            worst = [min(worst[0], min(s)), max(worst[1], max(s))]
            self.assertTrue(0.0 < gain_at_black(p) < math.inf, c)
            if grey:
                self.assertLess(abs(shift(0.0, p)), 1e-9, c)
        self.assertGreater(worst[0], smin)
        self.assertLess(worst[1], smax)

    def test_camera_raw_grid(self):
        """I2, I4: every Camera Raw combination is monotone with slope in [0.021, 3.56] and keeps grey."""
        vals = (-100, -50, 0, 50, 100) if SLOW else (-100, 0, 100)
        self.check([dict(zip(SLIDERS, v)) for v in itertools.product(vals, repeat=5)], EGRID, 0.02, 3.6, grey=True)

    def test_corners(self):
        """I4: Camera Raw +-100 x Zone +-3 x Pivot -2/0/+2 never solarizes (slope 0.0009 - 9.51)."""
        grid = EGRID if SLOW else EGRID[::2]
        ctrls = []
        for cr in itertools.product((-100, 100), repeat=5):
            for zs in itertools.product((-3.0, 3.0), repeat=4):
                for pivot in (-2.0, 0.0, 2.0):
                    c = dict(zip(SLIDERS, cr), zonePivot=pivot)
                    c.update({'zone%sExp' % z: E for z, E in zip(T.ZONES, zs)})
                    ctrls.append(c)
        self.check(ctrls, grid, 0.0, 9.6)

    @unittest.skipUnless(SLOW, 'SLOW=1')
    def test_zone_grid(self):
        """I4: Zone 5^4 at the default edges, slope 0.12 - 8.16."""
        vals = (-3.0, -1.5, 0.0, 1.5, 3.0)
        self.check([{'zone%sExp' % z: E for z, E in zip(T.ZONES, v)} for v in itertools.product(vals, repeat=4)],
                   EGRID, 0.1, 8.2)

    @unittest.skipUnless(SLOW, 'SLOW=1')
    def test_random_extremes(self):
        """I4: 4000 random panels (Zone +-6, edges +-8, falloff 0.5-6, Pivot +-3, Soft Clip) stay monotone."""
        rnd = random.Random(5)
        # under the Soft Clip asymptote the true slope (2^-50) is below what a double difference resolves
        self.check([random_controls(rnd) for _ in range(4000)], EGRID, -1e-12, 52.0)


class Colour(unittest.TestCase):
    def test_saturation_minus_100_greys_every_pixel(self):
        """Saturation -100 leaves no chroma at any Y, Y <= 0 included, with or without Soft Clip."""
        rnd = random.Random(21)
        for roof in (False, True):
            p = T.set_tone({'toneSaturation': -100, 'toneVibrance': rnd.uniform(-100, 100), 'softClip': roof},
                           REC709, True)
            pixels = [dm.mul(dm.MATS[SG3][0], [0.05, g, 1.0]) for g in (0.02, 0.04, 0.06, 0.08)]
            pixels += [[rnd.uniform(-1, 1) for _ in range(3)] for _ in range(300)]
            self.assertLess(min(x[1] for x in pixels), 0.0)
            for xyz in pixels:
                X, Y, Z = T.tone5(xyz, p)
                self.assertEqual((X - Y * T.SM_T5_WX, Z - Y * T.SM_T5_WZ), (0.0, 0.0), xyz)

    def test_vibrance_spares_skin(self):
        """Vibrance +100 gives skin at most 0.75 of the boost it would get unprotected, and far hues all of it."""
        p = T.set_tone({'toneVibrance': 100})

        def boost(name):
            xi = patch_xyz(name, PATCH_EV[name])
            return chroma(T.tone5(xi, p)) / chroma(xi) - 1.0

        kept = {n: boost(n) for n in ('skin', 'sky')}
        with mock.patch.object(T, 'SM_T5_SKIN_PROTECT', 0.0):
            bare = {n: boost(n) for n in ('skin', 'sky')}
        self.assertLessEqual(kept['skin'], 0.75 * bare['skin'])
        self.assertAlmostEqual(kept['sky'], bare['sky'], places=12)

    def test_a_push_never_drives_a_channel_negative(self):
        """With Y > 0 no Saturation, Vibrance or zone Sat push takes a channel of R below 0."""
        rnd = random.Random(22)
        for ref in (REC709, REC2020, P3D65):
            for _ in range(150):
                c = {'toneSaturation': rnd.uniform(0, 100), 'toneVibrance': rnd.uniform(0, 100)}
                for z in T.ZONES:
                    c['zone%sSat' % z] = rnd.uniform(0, 100)
                p = T.set_tone(c, ref, True)
                scale = 10.0 ** rnd.uniform(-3, 1)
                rgb = [rnd.uniform(0, 1) ** 3 * scale for _ in range(3)]
                out = dm.mul(dm.MATS[ref][1], T.tone5(dm.mul(dm.MATS[ref][0], rgb), p))
                self.assertGreaterEqual(min(out), -1e-12 * max(rgb), (c, rgb))
                lo = [rnd.uniform(-0.2, 1.0) for _ in range(3)]
                xyz = dm.mul(dm.MATS[ref][0], lo)
                if xyz[1] > 0.0:
                    out = dm.mul(dm.MATS[ref][1], T.tone5(xyz, p))
                    self.assertGreaterEqual(min(out), min(min(lo), 0.0) - 1e-12, (c, lo))

    def test_soft_clip_keeps_every_channel_under_the_roof(self):
        """With Soft Clip and Rec.709 output no channel reaches H, Saturation up to +100 included."""
        colours = ([1, 0, 0], [0, 1, 0], [0, 0, 1], [0.4287, 0.0369, 0.0452], [1.0, 0.35, 0.0], [1, 0, 1])
        for sat in (0, 50, 100):
            p = T.set_tone({'softClip': 1, 'softClipLevel': 2.5, 'toneSaturation': sat}, REC709, True)
            worst = 0.0
            for rgb in colours:
                xyz = dm.mul(dm.MATS[REC709][0], rgb)
                n = T.t5_norm(dm.mul(dm.MATS[REC2020][1], xyz))
                for i in range(121):
                    k = GREY * 2.0 ** (i * 0.1) / n
                    out = dm.mul(dm.MATS[REC709][1], T.tone5([v * k for v in xyz], p))
                    worst = max(worst, max(out) / p['roofLin'])
            self.assertLess(worst, 0.99, sat)

    def test_zone_sat_follows_its_zone(self):
        """Shadow Sat -100 greys what lies below +1 and leaves the sky at +3 alone."""
        p = T.set_tone(zone('Shadow', sat=-100))
        self.assertLess(chroma(T.tone5(patch_xyz('foliage', -3.0), p)), 1e-12)
        sky = patch_xyz('sky', 3.0)
        self.assertAlmostEqual(chroma(T.tone5(sky, p)), chroma(sky), places=12)


class Lut(unittest.TestCase):
    def lut_error(self, p, n=65, samples=8192):
        """Worst error, in 10-bit code values, of an n-point S-Log3 1D LUT of the neutral curve."""
        def f(x):
            y = dm.decode1(x, SLOG3)
            return dm.encode1(0.0 if y == 0.0 else y * 2.0 ** T.t5_gain(abs(y), p)[0], SLOG3)

        ys = [f(i / (n - 1.0)) for i in range(n)]
        worst = 0.0
        for j in range(samples + 1):
            x = j / float(samples)
            i = min(int(x * (n - 1)), n - 2)
            t = x * (n - 1) - i
            worst = max(worst, abs(ys[i] * (1.0 - t) + ys[i + 1] * t - f(x)) * 1023.0)
        return worst

    def test_65_points(self):
        """A 65-point S-Log3 LUT stays within 3.5 CV, except the measured cases of LUT_65_OVER."""
        cases = [((n, v), {n: v}) for n in SLIDERS for v in (-100, 100)]
        cases += [(('zone%sExp' % z, E, f), zone(z, E, falloff=f))
                  for z in T.ZONES for E in (-3.0, 3.0) for f in (0.5, 1.0, 2.0)]
        cases.append((('softClip', 2.5), {'softClip': 1, 'softClipLevel': 2.5}))
        for key, c in cases:
            self.assertLessEqual(self.lut_error(T.set_tone(c)), LUT_65_OVER.get(key, 3.5), key)


class ZoneFalseColour(unittest.TestCase):
    def colour_at(self, ev, p):
        return T.false_color_zones(patch_xyz('skin', ev), p)

    def mix(self, *zones):
        tints = [T.SM_FC_ZONE_TINT[T.ZONES.index(z)] for z in zones]
        return [sum(t[i] for t in tints) / len(tints) for i in range(3)]

    def assertColour(self, got, want):
        for a, b in zip(got, want):
            self.assertAlmostEqual(a, b, places=9)

    def test_the_default_bands(self):
        """Grey is half Shadow, half Light; deep shadows mix Black and Shadow, bright highlights Light and Specular."""
        p = T.set_tone({})
        self.assertColour(self.colour_at(0.0, p), self.mix('Shadow', 'Light'))
        self.assertColour(self.colour_at(-10.0, p), self.mix('Black', 'Shadow'))
        self.assertColour(self.colour_at(8.0, p), self.mix('Light', 'Specular'))
        self.assertColour(self.colour_at(-2.0, p), T.SM_FC_ZONE_TINT[1])

    def test_outside_every_zone_the_picture_is_grey(self):
        """Where no zone reaches, the view is a monochrome of the measured stops."""
        p = T.set_tone({'zoneShadowRange': -4.0, 'zoneLightRange': 3.0})
        self.assertColour(self.colour_at(0.0, p), [6.0 / 11.5] * 3)

    def test_it_reads_the_norm_after_blacks_and_ignores_exp(self):
        """The view measures the Rec.2020 norm after Blacks, as the zones do, and does not move with Exp."""
        p = T.set_tone({})
        red = patch_xyz('red', 0.5)
        grey = dm.mul(dm.MATS[REC2020][0], [GREY * 2.0 ** 0.5] * 3)
        self.assertColour(T.false_color_zones(red, p), T.false_color_zones(grey, p))
        self.assertEqual(T.false_color_zones(red, T.set_tone({'zoneLightExp': 3, 'zoneShadowExp': -2})),
                         T.false_color_zones(red, p))
        at = -3.6
        self.assertColour(self.colour_at(at, p), T.SM_FC_ZONE_TINT[1])
        crushed = self.colour_at(at, T.set_tone({'toneBlacks': -100}))
        self.assertNotEqual(crushed, self.colour_at(at, p))


if __name__ == '__main__':
    unittest.main()
