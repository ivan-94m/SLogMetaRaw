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


def develop(rgb, node_space, node_gamma, shot=(5600, 0, 800),
            temp=None, tint=None, ei=None, wb_mode=0, out_space=None, out_gamma=None,
            shadows=0.0, highlights=0.0, contrast=0.0, saturation=0.0, boost=0.0, decode_meta=False):
    shot_k, shot_t, shot_ei = shot
    temp = shot_k if temp is None else temp
    tint = shot_t if tint is None else tint
    ei = shot_ei if ei is None else ei
    out_space = node_space if out_space is None else out_space
    out_gamma = node_gamma if out_gamma is None else out_gamma
    if decode_meta:
        return list(rgb)
    lin = [decode1(c, node_gamma) * (ei / shot_ei) for c in rgb]
    xyz = mul(MATS[node_space][0], lin)
    k, t = (PRESETS[wb_mode], 0.0) if wb_mode in PRESETS else (temp, tint)
    ws, wt = mul(BR, white_xyz(shot_k, shot_t)), mul(BR, white_xyz(k, t))
    r = [ws[i] / wt[i] for i in range(3)]
    lms = mul(BR, xyz)
    xyz = mul(BRI, [lms[i] * r[i] for i in range(3)])
    wl = mul(BR, [0.95046, 1.0, 1.08906])
    nwy = mul(BRI, [wl[i] * r[i] for i in range(3)])[1]
    xyz = [c / nwy for c in xyz]
    ev = math.log2(max(xyz[1], 1e-6) / 0.18)
    wh, wsh = min(max(ev / 5, 0), 1), min(max(-ev / 5, 0), 1)
    kk = 2 ** (ev * contrast + highlights * 2 * wh * wh + shadows * 2 * wsh * wsh)
    xyz = [c * kk for c in xyz]
    rgbn = mul(MATS[node_space][1], xyz)
    mx, mn = max(rgbn), min(rgbn)
    sat_now = min(max((mx - mn) / mx, 0), 1) if mx > 1e-6 else 0
    sf = (1 + saturation) * (1 + boost * (1 - sat_now))
    yl = xyz[1]
    rgbn = [yl + (c - yl) * sf for c in rgbn]
    if out_space == node_space and out_gamma == node_gamma:
        return [encode1(c, node_gamma) for c in rgbn]
    o = mul(MATS[out_space][1], mul(MATS[node_space][0], rgbn))
    return [encode1(c, out_gamma) for c in o]
