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


def planck_xy(t):
    t = min(max(t, 1667), 25000)
    it = 1000 / t
    x = (-0.2661239 * it ** 3 - 0.2343589 * it ** 2 + 0.8776956 * it + 0.179910) if t <= 4000 \
        else (-3.0258469 * it ** 3 + 2.1070379 * it ** 2 + 0.2226347 * it + 0.240390)
    if t <= 2222: y = -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - 0.20219683
    elif t <= 4000: y = -0.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - 0.16748867
    else: y = 3.0817580 * x ** 3 - 5.87338670 * x ** 2 + 3.75112997 * x - 0.37001483
    return x, y


def xy_uv(x, y):
    d = -2 * x + 12 * y + 3
    return 4 * x / d, 6 * y / d


def uv_xy(u, v):
    d = 2 * u - 8 * v + 4
    return 3 * u / d, 2 * v / d


TINT_LIMIT = 100.0   # SM_TINT_LIMIT of DevelopMath.h
LMS_FLOOR = 0.02     # SM_LMS_FLOOR: the cone responses of a usable white


def white_xyz(k, tint):
    """Reference for sm_white_xyz: clamped tint, and never a non-physical white."""
    tint = min(max(tint, -TINT_LIMIT), TINT_LIMIT)
    px, py = planck_xy(k)
    u0, v0 = xy_uv(px, py)
    # a second point ON the locus: planck_xy clamps at 25000 K, where k * 1.01 would
    # land on the same point and leave the normal as 0/0
    k1 = k * 1.01
    u1, v1 = xy_uv(*planck_xy(k / 1.01 if k1 > 25000 else k1))
    du, dv = u1 - u0, v1 - v0
    l = math.hypot(du, dv)
    if not l > 0:
        return [px / py, 1.0, (1 - px - py) / py]
    n = (-dv / l, du / l)
    if n[1] < 0:
        n = (-n[0], -n[1])
    u, v = u0 + n[0] * tint / 3000, v0 + n[1] * tint / 3000
    d = 2 * u - 8 * v + 4                       # guarded, as sm_white_xyz is
    x, y = (3 * u / d, 2 * v / d) if d != 0 else (-1.0, -1.0)
    if not (y > 1e-6) or not (x > 0.0) or not (1 - x - y > 0.0):
        x, y = px, py
    return [x / y, 1.0, (1 - x - y) / y]


def white_lms(k, tint):
    """Reference for sm_white_lms: a white whose CONE RESPONSES are positive. Inside
    the spectral locus is not enough - Tint +100 at 3200 K gives Bradford S = -0.009
    and a von Kries ratio of -152. The tint walks back until the white is usable."""
    for _ in range(32):
        lms = mul(BR, white_xyz(k, tint))
        if min(lms) > LMS_FLOOR:
            return lms
        tint *= 0.75
    return mul(BR, white_xyz(k, 0.0))


def fix_levels(lin, node_space, level_space, level_gamma, gain, offset):
    """Reference for sm_fix_levels: affine remap of the code values, done in the
    camera encoding, reached by an exact round-trip from whatever the node is in."""
    same = level_space == node_space
    cam = lin if same else mul(MATS[level_space][1], mul(MATS[node_space][0], lin))
    cv = [encode1(c, level_gamma) * gain + offset for c in cam]
    cam = [decode1(c, level_gamma) for c in cv]
    return cam if same else mul(MATS[node_space][1], mul(MATS[level_space][0], cam))


# --- tone: the press, the toe and the chroma (sm_tone* of DevelopMath.h) ---------

TONE_GREY = 0.18
GREY = TONE_GREY
TONE_KNEE = 2.5                             # see SM_TONE_KNEE: grey 0.008 st, +3..top 0.195 st
TONE_CAP_SOFT = 4.0                         # soft minimum on the expansion's lift
TONE_E_BOT = -10.0
TONE_E_709 = 2.4739311883324122             # log2(1 / 0.18)
TONE_E_TOP_MIN, TONE_E_TOP_MAX = 4.0, 12.0
TONE_E_TOP_DEF = 10.0
TONE_EXPAND = 2.0                           # stops of lift at Highlights +100
TONE_MIX = 0.5
TONE_SHAD_OFF, TONE_SHAD_W, TONE_SHAD_AMP = 6.0, 1.8, 1.5


def tank_top(gamma):
    """Reference for sm_tank_top: top of the container a transfer curve records, in
    stops over 18% grey. S-Log3 +7.74, S-Log2 +6.26, S-Log +5.76."""
    try:
        top = math.log2(decode1(1.0, gamma) / GREY)
    except (ValueError, OverflowError):
        return TONE_E_TOP_DEF
    if not TONE_E_TOP_MIN <= top <= TONE_E_TOP_MAX:
        return TONE_E_TOP_DEF
    return top


def tone_norm(c):
    """Power norm: norm(x, x, x) = x exactly, and smooth, unlike max(RGB)."""
    den = sum(v * v for v in c)
    return sum(abs(v) ** 3 for v in c) / den if den > 1e-12 else 0.0


def tone_bell(ev, mid, width):
    z = (ev - mid) / width
    return math.exp(-z * z)


def tone_ceiling(e_top, h):
    """Where the top of the tank lands, in stops over grey. Linear in the slider, and
    the same travel both ways, so +H is the exact inverse of -H."""
    return e_top - abs(h) * (e_top - TONE_E_709)


def tone_asymptote(e_top, h):
    """K such that the curve sends the top of the tank exactly onto the ceiling.
    0 means 'identity', which is what h = 0 gives without a special case."""
    if abs(h) < 1e-6 or e_top <= TONE_E_709:
        return 0.0
    xt = GREY * 2 ** e_top
    xc = GREY * 2 ** tone_ceiling(e_top, h)
    q = (xt / xc) ** TONE_KNEE - 1.0
    return 0.0 if q <= 0 else xt / q ** (1.0 / TONE_KNEE)


def tone_curve(x, k, cap, expand):
    """Compression x / (1 + (x/k)^n)^(1/n) in soft-minimum form, or the MIRROR of the
    same displacement applied upwards and capped. Odd in x, f(0) = 0, f'(0) = 1,
    monotone either way round and bounded either way round."""
    if k <= 0:
        return x
    s = -1.0 if x < 0 else 1.0
    ax = abs(x)
    if ax < 1e-9:
        return x
    f = (ax ** -TONE_KNEE + k ** -TONE_KNEE) ** (-1.0 / TONE_KNEE)
    if not expand:
        return s * f
    drop = math.log2(ax / f)
    if drop < 1e-9:
        return x
    lift = (drop ** -TONE_CAP_SOFT + cap ** -TONE_CAP_SOFT) ** (-1.0 / TONE_CAP_SOFT)
    return s * ax * 2 ** lift


def tone(rgb, node_space, highlights, shadows, chroma_recover, e_top=TONE_E_TOP_DEF):
    rgb = list(rgb)
    if shadows != 0.0:
        n0 = tone_norm(rgb)
        if n0 > 1e-6:
            bell = tone_bell(math.log2(n0 / GREY), TONE_E_BOT + TONE_SHAD_OFF, TONE_SHAD_W)
            rgb = [c * 2 ** (shadows * TONE_SHAD_AMP * bell) for c in rgb]
    k = tone_asymptote(e_top, highlights)
    if k <= 0:
        return rgb                              # Highlights at 0: exact identity
    expand = 1 if highlights > 0 else 0
    cap = highlights * TONE_EXPAND
    keep = list(rgb)
    norm = tone_norm(rgb)
    if norm > 1e-6:
        t = tone_curve(norm, k, cap, expand) / norm
        keep = [c * t for c in rgb]
    film = [tone_curve(c, k, cap, expand) for c in rgb]
    w = (TONE_MIX + chroma_recover * (1.0 - TONE_MIX) if chroma_recover >= 0
         else TONE_MIX * (1.0 + chroma_recover))
    w = min(max(w, 0.0), 1.0)
    return [film[i] + (keep[i] - film[i]) * w for i in range(3)]


# --- gamut (sm_gamut_* of DevelopMath.h) ------------------------------------

GAMUT_THRESH = 0.7
GAMUT_KNEE = 3.0


def gamut_one(v, ac, t, a):
    d = (ac - v) / ac
    if d <= t + 1e-6:
        return v                      # the compressed distance tends to t + x = d
    x = d - t
    d = t + (x ** -GAMUT_KNEE + a ** -GAMUT_KNEE) ** (-1.0 / GAMUT_KNEE)
    return ac * (1.0 - d)


def gamut_compress(c):
    """Reference for sm_gamut_compress: the distance of each channel from the
    achromatic is compressed towards an asymptote of 1, which is exactly the point
    at which the channel would be zero - so it can never come out negative."""
    ac = max(c)
    if not ac > 1e-9:
        return list(c)
    t, a = GAMUT_THRESH, 1.0 - GAMUT_THRESH
    return [gamut_one(v, ac, t, a) for v in c]


# --- false colour (sm_fc_* of DevelopMath.h) --------------------------------

def neutral_uv(shot_k, shot_t, k, t):
    """CIE 1960 uv a neutral pixel lands on after the white balance, as neutralUV()."""
    d65 = [0.95046, 1.0, 1.08906]
    ws, wt = white_lms(shot_k, shot_t), white_lms(k, t)
    r = [ws[i] / wt[i] for i in range(3)]
    lms = mul(BR, d65)
    xyz = mul(BRI, [lms[i] * r[i] for i in range(3)])
    nwy = mul(BRI, [mul(BR, d65)[i] * r[i] for i in range(3)])[1]
    X, Y, Z = [c / nwy for c in xyz]
    d = X + 15 * Y + 3 * Z
    return (4 * X / d, 6 * Y / d) if d > 1e-9 else (0.0, 0.0)


def fc_calibration(k, t):
    """(u0, v0, ku, kv, tu, tv): the inverse of the sliders' response, as buildParams."""
    u0, v0 = neutral_uv(k, t, k, t)
    uk, vk = neutral_uv(k, t, k + 100.0, t)
    ut, vt = neutral_uv(k, t, k, t + 5.0)
    a, c = (uk - u0) / 100.0, (vk - v0) / 100.0
    b, e = (ut - u0) / 5.0, (vt - v0) / 5.0
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


def fc_band(dev, centre, mid, wide, limit, p1, p2, p3, n1, n2, n3, mono):
    a = abs(dev)
    # in tolerance, or so far out that it is the object's colour and not a cast
    if a <= centre or a > limit: return [mono, mono, mono]
    if dev > 0: return p1 if a <= mid else (p2 if a <= wide else p3)
    return n1 if a <= mid else (n2 if a <= wide else n3)


def false_color(xyz, mode, u, v, ku, kv, tu, tv):
    ev = math.log2(max(xyz[1], 1e-9) / 0.18)
    if mode == 1: return fc_exposure(ev)
    mono = min(max((ev + 6.0) / 11.5, 0.06), 0.92)
    if ev >= 5.5: return [0.96, 0.16, 0.10]
    if ev <= -4.0: return [0.11, 0.11, 0.13]
    d = xyz[0] + 15 * xyz[1] + 3 * xyz[2]
    if d < 1e-9: return [0.11, 0.11, 0.13]
    du, dv = 4 * xyz[0] / d - u, 6 * xyz[1] / d - v
    if mode == 2:
        return fc_band(-(ku * du + kv * dv), 75.0, 300.0, 1200.0, 2500.0,
                       [0.55, 0.86, 1.00], [0.15, 0.55, 1.00], [0.09, 0.18, 0.85],
                       [1.00, 0.88, 0.25], [1.00, 0.55, 0.10], [0.90, 0.20, 0.08], mono)
    return fc_band(-(tu * du + tv * dv), 2.0, 6.0, 15.0, 30.0,
                   [0.66, 1.00, 0.62], [0.22, 0.86, 0.26], [0.05, 0.58, 0.10],
                   [1.00, 0.70, 0.98], [0.92, 0.25, 0.85], [0.62, 0.05, 0.58], mono)


def fc_emit(c, node_space, node_gamma, out_space, out_gamma):
    convert = out_space != node_space or out_gamma != node_gamma
    space, gamma = (out_space, out_gamma) if convert else (node_space, node_gamma)
    lin = [decode1(x, 2) for x in c]
    return [encode1(x, gamma) for x in mul(MATS[space][1], mul(MATS[1][0], lin))]


def develop(rgb, node_space, node_gamma, shot=(5600, 0, 800),
            temp=None, tint=None, ei=None, wb_mode=0, out_space=None, out_gamma=None,
            shadows=0.0, highlights=0.0, contrast=0.0, saturation=0.0, boost=0.0, decode_meta=False,
            level_fix=0, level_space=0, level_gamma=0, level_gain=1.0, level_offset=0.0,
            fc_mode=0, fc_u=0.0, fc_v=0.0, fc_ku=0.0, fc_kv=0.0, fc_tu=0.0, fc_tv=0.0,
            chroma_recover=0.0, e_top=None):
    shot_k, shot_t, shot_ei = shot
    temp = shot_k if temp is None else temp
    tint = shot_t if tint is None else tint
    ei = shot_ei if ei is None else ei
    out_space = node_space if out_space is None else out_space
    out_gamma = node_gamma if out_gamma is None else out_gamma
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
    ws, wt = white_lms(shot_k, shot_t), white_lms(k, t)
    r = [ws[i] / wt[i] for i in range(3)]
    lms = mul(BR, xyz)
    xyz = mul(BRI, [lms[i] * r[i] for i in range(3)])
    wl = mul(BR, [0.95046, 1.0, 1.08906])
    nwy = mul(BRI, [wl[i] * r[i] for i in range(3)])[1]
    xyz = [c / nwy for c in xyz]
    if fc_mode:   # measured before the trims below, so it answers only to the three controls
        return fc_emit(false_color(xyz, fc_mode, fc_u, fc_v, fc_ku, fc_kv, fc_tu, fc_tv),
                       node_space, node_gamma, out_space, out_gamma)
    rgbn = mul(MATS[node_space][1], xyz)
    if contrast != 0.0:
        cn = tone_norm(rgbn)
        if cn > 1e-6:
            kk = 2 ** (math.log2(cn / GREY) * contrast)
            rgbn = [c * kk for c in rgbn]
    # the conversion happens BEFORE the press, so the press and the saturation work
    # in the space being written: "the peak a Rec.709 signal holds" means nothing
    # until we are in Rec.709. Neutrals are unaffected, chromatic pixels are not.
    convert = out_space != node_space or out_gamma != node_gamma
    sp = out_space if convert else node_space
    g = out_gamma if convert else node_gamma
    o = mul(MATS[out_space][1], mul(MATS[node_space][0], rgbn)) if convert else rgbn
    o = tone(o, sp, highlights, shadows, chroma_recover,
             tank_top(node_gamma) if e_top is None else e_top)
    mx, mn = max(o), min(o)
    sat_now = min(max((mx - mn) / mx, 0), 1) if mx > 1e-6 else 0
    sf = (1 + saturation) * (1 + boost * (1 - sat_now))
    yl = max(mul(MATS[sp][0], o)[1], 0.0)   # never desaturate towards a negative grey
    o = [yl + (c - yl) * sf for c in o]
    o = gamut_compress(o)      # last thing before the encode, on linear values
    return [encode1(c, g) for c in o]
