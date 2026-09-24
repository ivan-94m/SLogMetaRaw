# SPDX-License-Identifier: GPL-3.0-or-later
"""Python reference of the v5 colour stage (math/Color.h).

Every move is XYZ' = Y*W + m*(XYZ - Y*W) with W the D65 white: Y stays and the
chroma scales by m, for any Y. The channel limits are read in the gamut R
(p['refSpace']), which depends on the output only, so the result does not
depend on the node gamut (I7). The one exception is Highlights' path to white,
a mix toward the power norm in Rec.2020 (t5_hl_white), also node-independent.
"""
import math

from . import tone as T
from .tone import dm


def _p4(x):
    # x**4 raises OverflowError in Python; this overflows to inf as float32 does
    x2 = x * x
    return x2 * x2


def t5_sat(xyz, e, p):
    """m of Saturation, Vibrance (skin kept at SM_T5_SKIN_PROTECT) and zone Sat, softly
    limited where it would push a channel of R below 0."""
    X, Y, Z = xyz
    d = X + 15.0 * Y + 3.0 * Z
    sn = skin = 0.0
    vib = p['vib']
    if d > 1e-30:
        du, dv = 4.0 * X / d - T.SM_T5_UW, 9.0 * Y / d - T.SM_T5_VW
        s = math.hypot(du, dv)
        sn = s / (s + T.SM_T5_SAT_HALF)
        if vib > 0.0 and s > 1e-12:
            dh = abs(math.atan2(dv, du) - T.SM_T5_SKIN_HUE)
            dh = min(dh, 2.0 * math.pi - dh)
            skin = T.t5_ramp((T.SM_T5_SKIN_ZERO - dh) / (T.SM_T5_SKIN_ZERO - T.SM_T5_SKIN_FULL))
    m = (1.0 + p['sat']) * (1.0 + vib * (1.0 - sn) * ((1.0 - T.SM_T5_SKIN_PROTECT * skin) if vib > 0.0 else 1.0))
    for z in range(4):
        m *= 1.0 + p['zSat'][z] * T.t5_zone_weight(e, z, p)
    if m <= 1.0:
        return m
    if Y <= 0.0:
        return 1.0
    acc = 0.0
    for c in dm.mul(dm.MATS[p['refSpace']][1], xyz):
        if c < Y:
            acc += _p4((Y - c) / Y)
    if acc <= 0.0:
        return m
    rho = max(acc ** (-1.0 / T.SM_T5_GAMUT_P) - 1.0, 0.0)
    x = m - 1.0
    return 1.0 + (x / (1.0 + _p4(x / rho)) ** (1.0 / T.SM_T5_GAMUT_P) if rho > 0.0 else 0.0)


def t5_limit(xyz, m, H, space, soft=0.0):
    """m with every channel of the gamut `space` kept softly below H (0 once Y reaches H (1 + soft))."""
    Y = xyz[1]
    room = H * (1.0 + soft) - Y
    if room <= 0.0:
        return 0.0
    acc = 0.0
    for c in dm.mul(dm.MATS[space][1], xyz):
        if c > Y:
            acc += _p4((c - Y) / room)
    if acc > 0.0 and m > 0.0:
        m /= (1.0 + _p4(m * acc ** (1.0 / T.SM_T5_GAMUT_P))) ** (1.0 / T.SM_T5_GAMUT_P)
    return m


def t5_roof(xyz, m, tr, p):
    """m after the Soft Clip: purity 2^(k*tr) where the roof pulls down, then every channel of R
    kept softly below the roof H."""
    if tr < 0.0:
        k = T.SM_T5_ROOF_K * (1.0 + T.SM_T5_ROOF_GROW * (1.0 - 2.0 ** tr)) * p['roofPurity']
        m *= 2.0 ** (k * tr)
    return t5_limit(xyz, m, p['roofLin'], p['refSpace'])


def t5_chroma(xyz, m):
    """XYZ' = Y*W + m*(XYZ - Y*W)."""
    X, Y, Z = xyz
    return [Y * T.SM_T5_WX + m * (X - Y * T.SM_T5_WX), Y, Y * T.SM_T5_WZ + m * (Z - Y * T.SM_T5_WZ)]


OKLAB = ([[0.8189330101, 0.3618667424, -0.1288597137], [0.0329845436, 0.9293118715, 0.0361456387],
          [0.0482003018, 0.2643662691, 0.6338517070]],
         [[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
          [0.0259040371, 0.7827717662, -0.8086757660]],
         [[1.0, 0.3963377774, 0.2158037573], [1.0, -0.1055613458, -0.0638541728], [1.0, -0.0894841775, -1.2914855480]],
         [[1.2270138511, -0.5577999807, 0.2812561490], [-0.0405801784, 1.1122568696, -0.0716766787],
          [-0.0763812845, -0.4214819784, 1.5861632204]])


def oklab_chroma(xyz, m):
    """sm_oklab_chroma: chroma times m at constant Oklab hue and lightness."""
    l = [math.copysign(abs(c) ** (1.0 / 3.0), c) for c in dm.mul(OKLAB[0], xyz)]
    L, a, b = dm.mul(OKLAB[1], l)
    return dm.mul(OKLAB[3], [c ** 3 for c in dm.mul(OKLAB[2], [L, m * a, m * b])])


def t5_hl_white(xyz, hl, w, white_lin, space, out_space):
    """Where Highlights compresses (hl < 0): the path to white, chroma 2^(KAPPA hl) at constant hue, lowered
    further by w where a channel of `space` would pass the white (the display-white taper)."""
    m = 2.0 ** (T.SM_T5_HL_KAPPA * hl)
    if w > 0.0:
        m *= 1.0 - w * (1.0 - t5_limit(t5_chroma(xyz, m), 1.0, white_lin, space, T.SM_T5_HL_SOFT))
    c = dm.mul(dm.MATS[T.SM_T5_REF][1], xyz)     # the straight line goes to the norm: Y can be negative
    N = T.t5_norm(c)
    lin = dm.mul(dm.MATS[T.SM_T5_REF][0], [N + m * (v - N) for v in c])
    c = dm.mul(OKLAB[0], xyz)      # Oklab only for real colours: past the locus its cones go negative
    t = T.t5_ramp(min(c) / (0.1 * max(c))) if max(c) > 0.0 else 0.0
    if t <= 0.0:
        return lin
    ok = oklab_chroma(xyz, m)
    for a, b in zip(dm.mul(dm.MATS[out_space][1], lin), dm.mul(dm.MATS[out_space][1], ok)):
        if b < 0.0:            # on the gamut's edge the curved path can step outside it: the straight line cannot
            a = max(a, 0.0)
            t = min(t, 0.98 * a / (a - b))
    return [a + t * (b - a) for a, b in zip(lin, ok)]


def t5_color(xyz, e, tr, p):
    """sm_t5_color on the toned XYZ; e and tr come from the tone stage (t5_gain)."""
    m = t5_sat(xyz, e, p) if p['colorOn'] else 1.0
    if p['roofOn']:
        m = t5_roof(xyz, m, tr, p)
    return t5_chroma(xyz, m)
