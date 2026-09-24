# SPDX-License-Identifier: GPL-3.0-or-later
"""Python reference of the SLogMetaRaw develop math (ofx/SLogMetaRaw/DevelopMath.h)."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
from gamut_matrices import matrices  # noqa: E402

MATS = [(m, mi) for _name, m, mi in matrices()]  # index = space code
BR = [[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]]
BRI = [[0.98699291, -0.14705426, 0.15996265], [0.43230527, 0.51836027, 0.04929123],
       [-0.00852866, 0.04004282, 0.96848669]]
PRESETS = {1: 5600, 2: 6500, 3: 7500, 4: 3200, 5: 4000, 6: 5500}


def mul(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def spow(x, p):
    return -((-x) ** p) if x < 0 else x ** p


def slog_enc(r):
    y = 0.432699 * math.log10(r + 0.037584) + 0.616596 + 0.03 if r >= 0 else r * 5 + 0.030001222851889303
    return (y * 876 + 64) / 1023


def slog_dec(x):
    y = (x * 1023 - 64) / 876
    return 10 ** ((y - 0.616596 - 0.03) / 0.432699) - 0.037584 if y >= 0.030001222851889303 \
        else (y - 0.030001222851889303) / 5


def encode1(y, g):
    if g == 0: return y * 10.44426855 if y <= 0.00262409 else (math.log2(y + 0.0075) + 7) * 0.07329248
    if g == 2: return spow(y, 1 / 2.2)
    if g == 3: return spow(y, 1 / 2.4)
    if g == 4: return spow(y, 1 / 2.6)
    if g == 5: return 4.5 * y if y < 0.018 else 1.099 * y ** 0.45 - 0.099
    if g == 6: return 12.92 * y if y <= 0.0031308 else 1.055 * y ** (1 / 2.4) - 0.055
    if g == 7: return slog_enc(y / 0.9)
    if g == 8: return slog_enc(y * 155 / 219 / 0.9)
    if g == 9: return (420 + math.log10((y + 0.01) / 0.19) * 261.5) / 1023 if y >= 0.01125 \
        else (y * (171.2102946929 - 95) / 0.01125 + 95) / 1023
    if g == 10: return 10.5402377416545 * y + 0.0729055341958355 if y <= 0.0078125 else (math.log2(y) + 9.72) / 17.52
    return y


def decode1(x, g):
    if g == 0: return x / 10.44426855 if x <= 0.02740668 else 2 ** (x / 0.07329248 - 7) - 0.0075
    if g == 2: return spow(x, 2.2)
    if g == 3: return spow(x, 2.4)
    if g == 4: return spow(x, 2.6)
    if g == 5: return x / 4.5 if x < 0.081 else ((x + 0.099) / 1.099) ** (1 / 0.45)
    if g == 6: return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    if g == 7: return slog_dec(x) * 0.9
    if g == 8: return slog_dec(x) * 0.9 * 219 / 155
    if g == 9: return 10 ** ((x * 1023 - 420) / 261.5) * 0.19 - 0.01 if x >= 171.2102946929 / 1023 \
        else (x * 1023 - 95) * 0.01125 / (171.2102946929 - 95)
    if g == 10: return (x - 0.0729055341958355) / 10.5402377416545 if x <= 0.155251141552511 else 2 ** (x * 17.52 - 9.72)
    return x


def xy_uv(x, y):
    d = -2 * x + 12 * y + 3
    return 4 * x / d, 6 * y / d


def uv_xy(u, v):
    d = 2 * u - 8 * v + 4
    return 3 * u / d, 2 * v / d


WB_KMIN, WB_KMAX, WB_TINT_MAX = 1500.0, 15000.0, 150.0


def locus_uv(t):
    """Planckian locus in CIE 1960 uv (Krystek 1985) and its unit normal towards green, as sm_locus_uv."""
    t = min(max(t, WB_KMIN), WB_KMAX)
    au = 0.860117757 + 1.54118254e-4 * t + 1.28641212e-7 * t * t
    bu = 1.0 + 8.42420235e-4 * t + 7.08145163e-7 * t * t
    av = 0.317398726 + 4.22806245e-5 * t + 4.20481691e-8 * t * t
    bv = 1.0 - 2.89741816e-5 * t + 1.61456053e-7 * t * t
    du = ((1.54118254e-4 + 2 * 1.28641212e-7 * t) * bu - au * (8.42420235e-4 + 2 * 7.08145163e-7 * t)) / bu ** 2
    dv = ((4.22806245e-5 + 2 * 4.20481691e-8 * t) * bv - av * (-2.89741816e-5 + 2 * 1.61456053e-7 * t)) / bv ** 2
    l = math.hypot(du, dv)
    n = (-dv / l, du / l)
    if n[1] < 0:
        n = (-n[0], -n[1])
    return au / bu, av / bv, n


def uv_xyz(u, v):
    x, y = uv_xy(u, v)
    return [x / y, 1.0, (1 - x - y) / y]


def bradford_s(u, v):
    return mul(BR, uv_xyz(u, v))[2]


def green_limit(u, v, n):
    """Largest green Duv that leaves the white's Bradford S cone 30% of its value on the locus."""
    target = 0.3 * bradford_s(u, v)
    lo, hi = 0.0, 0.2
    for _ in range(60):
        m = 0.5 * (lo + hi)
        if bradford_s(u + n[0] * m, v + n[1] * m) > target:
            lo = m
        else:
            hi = m
    return lo


def white_xyz(k, tint):
    u, v, n = locus_uv(k)
    d = min(max(tint, -WB_TINT_MAX), WB_TINT_MAX) / 3000
    if d > 0:
        lim = green_limit(u, v, n)
        a, b = 0.5 * lim, 0.5 * lim
        if d > a:
            d = a + b * (1 - math.exp(-(d - a) / b))
    return uv_xyz(u + n[0] * d, v + n[1] * d)


def fix_levels(lin, node_space, level_space, level_gamma, gain, offset):
    """Reference for sm_fix_levels: affine remap of the code values, done in the
    camera encoding, reached by an exact round-trip from whatever the node is in."""
    same = level_space == node_space
    cam = lin if same else mul(MATS[level_space][1], mul(MATS[node_space][0], lin))
    cv = [encode1(c, level_gamma) * gain + offset for c in cam]
    cam = [decode1(c, level_gamma) for c in cv]
    return cam if same else mul(MATS[node_space][1], mul(MATS[level_space][0], cam))


# --- false colour (math/FalseColor.h) -------------------------------------

def neutral_uv(shot_k, shot_t, k, t):
    """CIE 1960 uv a neutral pixel lands on after the white balance, as neutralUV()."""
    d65 = [0.95046, 1.0, 1.08906]
    ws, wt = mul(BR, white_xyz(shot_k, shot_t)), mul(BR, white_xyz(k, t))
    r = [ws[i] / wt[i] for i in range(3)]
    lms = mul(BR, d65)
    xyz = mul(BRI, [lms[i] * r[i] for i in range(3)])
    nwy = mul(BRI, [mul(BR, d65)[i] * r[i] for i in range(3)])[1]
    X, Y, Z = [c / nwy for c in xyz]
    d = X + 15 * Y + 3 * Z
    return (4 * X / d, 6 * Y / d) if d > 1e-9 else (0.0, 0.0)


def fc_calibration(k, t):
    """(u0, v0, ku, kv, tu, tv): the inverse of the sliders' response, as buildParams."""
    dk = 100.0 if k + 100.0 <= WB_KMAX else -100.0
    dt = 5.0 if t + 5.0 <= WB_TINT_MAX else -5.0
    u0, v0 = neutral_uv(k, t, k, t)
    uk, vk = neutral_uv(k, t, k + dk, t)
    ut, vt = neutral_uv(k, t, k, t + dt)
    a, c = (uk - u0) / dk, (vk - v0) / dk
    b, e = (ut - u0) / dt, (vt - v0) / dt
    det = a * e - b * c
    return u0, v0, e / det, -b / det, -c / det, a / det


def fc_exposure(ev):
    if ev >= 5.5: return [0.96, 0.16, 0.10]
    if ev >= 4.0: return [1.00, 0.88, 0.12]
    if 0.70 <= ev <= 1.30: return [1.00, 0.56, 0.72]
    if -0.33 <= ev <= 0.33: return [0.13, 0.82, 0.20]
    if ev <= -6.0: return [0.42, 0.12, 0.62]
    if ev <= -4.0: return [0.10, 0.28, 0.88]
    g = min(max((ev + 6.0) / 11.5, 0.06), 0.92)
    return [g, g, g]


# Hues of the white-balance views, as CineMatch paints them (HSL): cool, warm, green, magenta
FC_HUE = {'cool': 0.586, 'warm': 0.08, 'green': 0.30, 'magenta': 0.85}


def hsl_rgb(h, s, l):
    q = l * (1.0 + s) if l < 0.5 else l + s - l * s
    p = 2.0 * l - q

    def channel(t):
        t = t - math.floor(t)
        if t < 1.0 / 6.0:
            return p + (q - p) * 6.0 * t
        if t < 0.5:
            return q
        if t < 2.0 / 3.0:
            return p + (q - p) * (2.0 / 3.0 - t) * 6.0
        return p
    return [channel(h + 1.0 / 3.0), channel(h), channel(h - 1.0 / 3.0)]


def fc_balance(xyz, mode, u, v, ku, kv, tu, tv, ev, mono):
    """Temperature (2) and tint (3) views: the picture in grey, a pixel coloured only when its cast lies
    on this slider's axis - orange/blue, green/magenta - with its saturation boosted up to 8x near
    neutral as CineMatch does, and faded out where the pixel is too dark or too bright to judge."""
    d = xyz[0] + 15 * xyz[1] + 3 * xyz[2]
    rgb = [max(c, 0.0) for c in mul(MATS[1][1], xyz)]
    mx, mn = max(rgb), min(rgb)
    if d < 1e-9 or mx <= 0.0:
        return [mono] * 3
    du, dv = 4 * xyz[0] / d - u, 6 * xyz[1] / d - v
    kelvin = -(ku * du + kv * dv) / 100.0     # > 0: reads cool, wants warming
    tint = -(tu * du + tv * dv) / 5.0         # > 0: reads green
    if (abs(kelvin) >= abs(tint)) != (mode == 2):
        return [mono] * 3
    hi, lo = 1.0, (mn / mx) ** (1.0 / 2.2)    # display-encoded, normalised: exposure does not matter
    r = (hi - lo) / (hi + lo)
    sat = min(max(r * (8.0 - 7.0 * r), 0.0), 1.0)
    sat *= min(max((ev + 6.0) / 2.0, 0.0), 1.0) * min(max(5.5 - ev, 0.0), 1.0)
    if mode == 2:
        hue = FC_HUE['cool'] if kelvin > 0 else FC_HUE['warm']
    else:
        hue = FC_HUE['green'] if tint > 0 else FC_HUE['magenta']
    return hsl_rgb(hue, sat, mono)


def false_color(xyz, mode, u, v, ku, kv, tu, tv):
    ev = math.log2(max(xyz[1], 1e-9) / 0.18)
    if mode == 1: return fc_exposure(ev)
    mono = min(max((ev + 6.0) / 11.5, 0.06), 0.92)
    return fc_balance(xyz, mode, u, v, ku, kv, tu, tv, ev, mono)


def fc_emit(c, node_space, node_gamma, out_space, out_gamma):
    convert = out_space != node_space or out_gamma != node_gamma
    space, gamma = (out_space, out_gamma) if convert else (node_space, node_gamma)
    lin = [decode1(x, 2) for x in c]
    return [encode1(x, gamma) for x in mul(MATS[space][1], mul(MATS[1][0], lin))]


def develop(rgb, node_space, node_gamma, shot=(5600, 0, 800),
            temp=None, tint=None, ei=None, wb_mode=0, out_space=None, out_gamma=None,
            tone=None, decode_meta=False,
            level_fix=0, level_space=0, level_gamma=0, level_gain=1.0, level_offset=0.0,
            fc_mode=0, fc_u=0.0, fc_v=0.0, fc_ku=0.0, fc_kv=0.0, fc_tu=0.0, fc_tv=0.0):
    """sm_develop. tone: the Toni and Zone panel values by OFX name (tests/model/tone.CONTROLS)."""
    from model import tone as T   # the tone model imports this module: import it late
    shot_k, shot_t, shot_ei = shot
    temp = shot_k if temp is None else temp
    tint = shot_t if tint is None else tint
    ei = shot_ei if ei is None else ei
    out_space = node_space if out_space is None else out_space
    out_gamma = node_gamma if out_gamma is None else out_gamma
    convert = out_space != node_space or out_gamma != node_gamma
    if decode_meta and not level_fix:
        return list(rgb)
    lin = [decode1(c, node_gamma) for c in rgb]
    if level_fix:
        lin = fix_levels(lin, node_space, level_space, level_gamma, level_gain, level_offset)
    if decode_meta:   # develop off, data level only
        return [encode1(c, node_gamma) for c in lin]
    lin = [c * (ei / shot_ei) for c in lin]
    xyz = mul(MATS[node_space][0], lin)
    k, t = (PRESETS[wb_mode], 0.0) if wb_mode in PRESETS else (temp, tint)
    ws, wt = mul(BR, white_xyz(shot_k, shot_t)), mul(BR, white_xyz(k, t))
    r = [ws[i] / wt[i] for i in range(3)]
    lms = mul(BR, xyz)
    xyz = mul(BRI, [lms[i] * r[i] for i in range(3)])
    wl = mul(BR, [0.95046, 1.0, 1.08906])
    nwy = mul(BRI, [wl[i] * r[i] for i in range(3)])[1]
    xyz = [c / nwy for c in xyz]
    p = T.set_tone(tone or {}, out_space, convert, ei / shot_ei)
    p['outGamut'] = out_space          # the gamut the node writes: the path to white keeps it non-negative
    if fc_mode:   # measured before the trims, so it answers only to its own controls
        view = (T.false_color_zones(xyz, p) if fc_mode == 4
                else false_color(xyz, fc_mode, fc_u, fc_v, fc_ku, fc_kv, fc_tu, fc_tv))
        return fc_emit(view, node_space, node_gamma, out_space, out_gamma)
    if T.active(p):
        xyz = T.tone5(xyz, p)
    space, gamma = (out_space, out_gamma) if convert else (node_space, node_gamma)
    return [encode1(c, gamma) for c in mul(MATS[space][1], xyz)]
