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


def white_xyz(k, tint):
    u0, v0 = xy_uv(*planck_xy(k))
    u1, v1 = xy_uv(*planck_xy(k * 1.01))
    du, dv = u1 - u0, v1 - v0
    l = math.hypot(du, dv)
    n = (-dv / l, du / l)
    if n[1] < 0:
        n = (-n[0], -n[1])
    x, y = uv_xy(u0 + n[0] * tint / 3000, v0 + n[1] * tint / 3000)
    return [x / y, 1.0, (1 - x - y) / y]


def fix_levels(lin, node_space, level_space, level_gamma, gain, offset):
    """Reference for sm_fix_levels: affine remap of the code values, done in the
    camera encoding, reached by an exact round-trip from whatever the node is in."""
    same = level_space == node_space
    cam = lin if same else mul(MATS[level_space][1], mul(MATS[node_space][0], lin))
    cv = [encode1(c, level_gamma) * gain + offset for c in cam]
    cam = [decode1(c, level_gamma) for c in cv]
    return cam if same else mul(MATS[node_space][1], mul(MATS[level_space][0], cam))


# --- tone: shoulder, toe and chroma (sm_tone* of DevelopMath.h) -------------

TONE_KNEE, TONE_PURITY, TONE_PURITY_GROW = 3.0, 0.5, 1.0
TONE_SHAD_MID, TONE_SHAD_W, TONE_SHAD_AMP = -4.0, 1.8, 1.5
TONE_HIGH_MID, TONE_HIGH_W, TONE_HIGH_AMP = 3.5, 1.6, 1.0


def tone_norm(c):
    """Power norm: norm(x, x, x) = x exactly, and smooth, unlike max(RGB)."""
    den = sum(v * v for v in c)
    return sum(abs(v) ** 3 for v in c) / den if den > 1e-12 else 0.0


def tone_bell(ev, mid, width):
    z = (ev - mid) / width
    return math.exp(-z * z)


def tone(rgb, node_space, highlights, shadows, chroma_recover):
    norm = tone_norm(rgb)
    if norm <= 1e-6:
        return list(rgb)
    ev = math.log2(norm / 0.18)
    lift = (shadows * TONE_SHAD_AMP * tone_bell(ev, TONE_SHAD_MID, TONE_SHAD_W)
            + max(highlights, 0.0) * TONE_HIGH_AMP * tone_bell(ev, TONE_HIGH_MID, TONE_HIGH_W))
    t = 2 ** lift
    a = max(-highlights, 0.0)
    if a > 0.0:
        # soft-minimum form, see sm_tone: never raises a large number to TONE_KNEE
        L = norm * t
        t = (L ** -TONE_KNEE + a ** TONE_KNEE) ** (-1.0 / TONE_KNEE) / norm
    out = [c * t for c in rgb]
    k = TONE_PURITY * (1.0 + TONE_PURITY_GROW * max(1.0 - t, 0.0)) * 2 ** (-chroma_recover)
    purity = t ** k if t < 1.0 else 1.0
    purity -= max(chroma_recover, 0.0) * max(lift, 0.0) * 0.4
    if purity < 1.0:
        purity = min(max(purity, 0.0), 1.0)
        yl = mul(MATS[node_space][0], out)[1]
        out = [yl + (c - yl) * purity for c in out]
    return out


# --- false colour (sm_fc_* of DevelopMath.h) --------------------------------

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
            chroma_recover=0.0):
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
    ws, wt = mul(BR, white_xyz(shot_k, shot_t)), mul(BR, white_xyz(k, t))
    r = [ws[i] / wt[i] for i in range(3)]
    lms = mul(BR, xyz)
    xyz = mul(BRI, [lms[i] * r[i] for i in range(3)])
    wl = mul(BR, [0.95046, 1.0, 1.08906])
    nwy = mul(BRI, [wl[i] * r[i] for i in range(3)])[1]
    xyz = [c / nwy for c in xyz]
    if fc_mode:   # measured before the trims below, so it answers only to the three controls
        return fc_emit(false_color(xyz, fc_mode, fc_u, fc_v, fc_ku, fc_kv, fc_tu, fc_tv),
                       node_space, node_gamma, out_space, out_gamma)
    ev = math.log2(max(xyz[1], 1e-6) / 0.18)
    kk = 2 ** (ev * contrast)
    xyz = [c * kk for c in xyz]
    rgbn = tone(mul(MATS[node_space][1], xyz), node_space, highlights, shadows, chroma_recover)
    mx, mn = max(rgbn), min(rgbn)
    sat_now = min(max((mx - mn) / mx, 0), 1) if mx > 1e-6 else 0
    sf = (1 + saturation) * (1 + boost * (1 - sat_now))
    yl = mul(MATS[node_space][0], rgbn)[1]
    rgbn = [yl + (c - yl) * sf for c in rgbn]
    if out_space == node_space and out_gamma == node_gamma:
        return [encode1(c, node_gamma) for c in rgbn]
    o = mul(MATS[out_space][1], mul(MATS[node_space][0], rgbn))
    return [encode1(c, out_gamma) for c in o]
