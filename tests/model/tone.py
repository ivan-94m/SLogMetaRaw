# SPDX-License-Identifier: GPL-3.0-or-later
"""Python reference of the v5 tone engine (math/Tone.h, math/ToneHost.h, fcMode 4).

Kernel side, per pixel: t5_norm, t5_log, t5_ramp, t5_h, t5_blacks, t5_zone,
t5_softplus2, t5_shoulder, t5_curve, tone5 (= sm_tone5) and false_color_zones.
Host side: set_tone (= sm_set_tone), computed in double from the raw panel
values, shoulder_policy (Highlights) and zone_policy, the slot builder shared
with the Detail node.

A curve (SMToneCurve) is a mapping with conC, conPivot, hlE, hlStart, zoneE[7],
zoneEdge[7], zoneK[7], zoneFill[7], roofOn, roofStops, roofRenorm. It runs
Contrast, the Highlights shoulder, the slots, Soft Clip. The slots, in this
fixed order; slot i acts upwards when i < SM_T5_UP, downwards otherwise
(slot 2 is free: Highlights is the shoulder):

    0 Specular    zone      4 Black     zone
    1 Whites      slider    5 Shadows   slider
    2 -                     6 Shadow    zone
    3 Light       zone

Tone fields of DevelopParams, as set_tone returns them:
    toneOn      Blacks, Contrast, the shoulder or some slot moves the luminance
    blkA        Blacks veil amplitude: > 0 takes veil away, < 0 adds it, 0 off
    blkRenorm   log2 gain putting grey back after the veil, faded out above grey
    conC        Contrast c = 2^(v/100) - 1; conPivot its pivot in stops
    hlE         Highlights shoulder T - t = hlE * D(t - hlStart); 0 = off
    hlStart     where it starts: grey taken through Contrast
    zoneE       slot exposure in stops; 0 = slot off, and its other fields are 0
    zoneEdge    slot edge taken through Contrast and the shoulder, so it stays
                put in scene stops
    zoneK       rho/psi slope limiter k; zoneFill the C2 entry width f'/4
    roofOn      Soft Clip; roofStops its level h, roofRenorm the lift keeping grey
    roofPurity  2^(-softClipColor/100); roofLin the linear roof H
    hlAmount    Highlights < 0: its eased amount, the weight of the white taper
    hlWhiteLin  Bianco (softClipLevel) linear: where the taper keeps channels
    hlTaperSpace  the gamut the taper reads: the output one when converting to
                a display gamut, else Rec.709
    colorOn     Saturation, Vibrance or a zone Sat is not 0
    refSpace    gamut R of the colour stage
    sat, vib    Saturation and Vibrance, -1..1
    zSat        zone Sat, -1..1, in ZONES order (Black, Shadow, Light, Specular)
    zNomEdge    zone Range and 1/Falloff in scene stops, as the panel has them:
    zNomInvF    the weights of zone Sat and of the Zone false colour
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import develop_model as dm  # noqa: E402

SM_T5_GREY = 0.18
SM_T5_EPS = SM_T5_GREY * 2.0 ** -16
SM_T5_DELTA = 0.25
SM_T5_RMAX = 1.0 / (1.0 - SM_T5_DELTA)
SM_T5_W = SM_T5_RMAX * SM_T5_DELTA / 2.0
SM_T5_CON_R = 4.0
SM_T5_BLK_PHI = SM_T5_GREY * 2.0 ** -5
SM_T5_ROOF_N = 3.0
SM_T5_ROOF_K = 0.5
SM_T5_ROOF_GROW = 1.0
SM_T5_SAT_HALF = 0.05
SM_T5_SKIN_HUE = math.radians(33.0)
SM_T5_SKIN_FULL = math.radians(10.0)
SM_T5_SKIN_ZERO = math.radians(30.0)
SM_T5_SKIN_PROTECT = 0.7
SM_T5_GAMUT_P = 4.0
SM_T5_REF = 2
SM_T5_SLOTS = 7
SM_T5_UP = 4
# D65 exactly as the gamut matrices have it (xy 0.3127, 0.3290): RGB (Y, Y, Y) is then Y*W in every gamut,
# which Saturation -100 and the channel limits rely on (the rounded 0.95046 leaves a 4e-6 cast)
SM_T5_WX = 0.3127 / 0.3290
SM_T5_WZ = (1.0 - 0.3127 - 0.3290) / 0.3290
SM_T5_UW = 4.0 * SM_T5_WX / (SM_T5_WX + 15.0 + 3.0 * SM_T5_WZ)
SM_T5_VW = 9.0 / (SM_T5_WX + 15.0 + 3.0 * SM_T5_WZ)
SM_T5_ZONE_DIR = (-1.0, -1.0, 1.0, 1.0)
# Highlights shoulder: D(u) = [sp(r (psi(u) - m)) - sp(-r m)] / r, psi the C2 entry of width f
SM_T5_HL_FILL = 2.0
SM_T5_HL_RATE = 1.4
SM_T5_HL_MID = 0.9
SM_T5_HL_SP0 = math.log2(1.0 + 2.0 ** -(SM_T5_HL_RATE * SM_T5_HL_MID))
SM_T5_HL_KAPPA = 0.12
SM_T5_HL_SOFT = 0.25

# host only (sm_set_tone)
SM_T5_SMIN = 0.35
SM_T5_SMAX_ZONE = 1.0 / SM_T5_SMIN
SM_T5_SMAX_CR = 2.0
SM_T5_F_MIN = 0.05
SM_T5_BLK_CRUSH = 3.0
SM_T5_BLK_LIFT = 1.0
SM_T5_HL_START = 0.0
SM_T5_HL_TOP = 6.0
SM_T5_HL_SMIN = 0.06
SM_T5_HL_CPLUS = 0.5
SM_T5_HL_MINPULL = 1.5

# Zone false colour, display Rec.709 gamma 2.2 like the other views: Black, Shadow, Light, Specular
SM_FC_ZONE_TINT = ((0.00, 0.47, 0.55), (0.93, 0.28, 0.80), (1.00, 0.55, 0.05), (0.55, 1.00, 0.95))

ZONES = ('Black', 'Shadow', 'Light', 'Specular')
ZONE_SLOT = (4, 6, 3, 0)
ZONE_RANGE = (-4.0, 1.0, -1.0, 4.0)
ZONE_FALLOFF = (1.0, 2.0, 2.0, 1.0)
# slider: slot, edge, falloff, stops at 100 (Highlights is the shoulder, not a slot)
SLIDER_SLOT = {'toneWhites': (1, 3.5, 1.0, 1.0), 'toneShadows': (5, -1.0, 2.0, 2.0)}

CONTROLS = {n: (-100.0, 100.0, 0.0) for n in (
    'toneContrast', 'toneHighlights', 'toneShadows', 'toneWhites', 'toneBlacks', 'toneVibrance', 'toneSaturation')}
CONTROLS['zonePivot'] = (-4.0, 4.0, 0.0)
for _z, _r, _f in zip(ZONES, ZONE_RANGE, ZONE_FALLOFF):
    CONTROLS['zone%sExp' % _z] = (-6.0, 6.0, 0.0)
    CONTROLS['zone%sSat' % _z] = (-100.0, 100.0, 0.0)
    CONTROLS['zone%sRange' % _z] = (-10.0, 10.0, _r)
    CONTROLS['zone%sFalloff' % _z] = (0.5, 6.0, _f)
CONTROLS['softClip'] = (0.0, 1.0, 0.0)
CONTROLS['softClipLevel'] = (1.0, 10.0, 2.5)
CONTROLS['softClipColor'] = (-100.0, 100.0, 0.0)

CURVE_FIELDS = ('conC', 'conPivot', 'hlE', 'hlStart', 'zoneE', 'zoneEdge', 'zoneK', 'zoneFill', 'roofOn',
                'roofStops', 'roofRenorm')
TONE_FIELDS = ('toneOn', 'blkA', 'blkRenorm') + CURVE_FIELDS + (
    'roofPurity', 'roofLin', 'hlAmount', 'hlWhiteLin', 'hlTaperSpace', 'colorOn', 'refSpace', 'sat', 'vib', 'zSat',
    'zNomEdge', 'zNomInvF')


# ---------------------------------------------------------------- per pixel

def t5_norm(rgb):
    """Power norm sum|c|^3 / sum c^2, so norm(x, x, x) = x; divided by max|c| first so neither sum overflows."""
    mx = max(abs(rgb[0]), abs(rgb[1]), abs(rgb[2]))
    if mx <= 1e-30:
        return 0.0
    x, y, z = rgb[0] / mx, rgb[1] / mx, rgb[2] / mx
    return mx * (abs(x) * x * x + abs(y) * y * y + abs(z) * z * z) / (x * x + y * y + z * z)


def t5_log(n):
    """log2(sqrt(n^2 + eps^2) / grey): a soft floor at -16 EV, so the gain stays finite at black."""
    a, b = max(n, SM_T5_EPS), min(n, SM_T5_EPS)
    q = b / a
    return math.log2(a / SM_T5_GREY) + 0.5 * math.log2(1.0 + q * q)


def t5_ramp(u):
    """C2 ramp from 0 at u = 0 to 1 at u = 1, linear at slope SM_T5_RMAX in the middle."""
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    if u < SM_T5_DELTA:
        t = u / SM_T5_DELTA
        return SM_T5_RMAX * SM_T5_DELTA * (t * t * t - 0.5 * t * t * t * t)
    if u > 1.0 - SM_T5_DELTA:
        t = (1.0 - u) / SM_T5_DELTA
        return 1.0 - SM_T5_RMAX * SM_T5_DELTA * (t * t * t - 0.5 * t * t * t * t)
    return SM_T5_RMAX * (u - 0.5 * SM_T5_DELTA)


def t5_h(x):
    """(1 - e^-x) / x through tanh: the direct form cancels in float32 near 0."""
    if x < 1e-4:
        return 1.0 - 0.5 * x + x * x / 6.0
    return math.tanh(0.5 * x) * (1.0 + math.exp(-x)) / x


def t5_blacks(n, a, renorm):
    """log2 gain of the Blacks veil at norm n."""
    if a == 0.0:
        return 0.0
    w = 1.0 - t5_ramp(0.5 * math.log2(n / SM_T5_GREY)) if n > SM_T5_GREY else 1.0
    return math.log2(1.0 - a * t5_h(n / SM_T5_BLK_PHI)) + w * renorm


def t5_zone(t, edge, dirn, k, fill):
    """rho of one slot at t: 0 on the still side, 1 past the band; the slot moves t by E * rho."""
    d = (t - edge) * dirn
    if d <= 0.0:
        return 0.0
    if d < fill:
        u = d / fill
        psi = fill * (u * u * u - 0.5 * u * u * u * u)
    else:
        psi = d - 0.5 * fill
    x = k * psi
    if x <= 1.0 - SM_T5_W:
        return x
    if x >= 1.0 + SM_T5_W:
        return 1.0
    v = (x - (1.0 - SM_T5_W)) / (2.0 * SM_T5_W)
    return x - 2.0 * SM_T5_W * (v * v * v - 0.5 * v * v * v * v)


def t5_softplus2(y):
    return max(y, 0.0) + math.log2(1.0 + 2.0 ** -abs(y))


def t5_shoulder(t, c):
    """(T - t, entry weight) of the Highlights shoulder at t, after Contrast: hlE * D(t - hlStart), with D' rising
    from 0 to 1, and psi'(u) in [0, 1], the weight the colour stage fades in with. Both 0 at and below the start."""
    u = t - c['hlStart']
    if not u > 0.0 or c['hlE'] == 0.0:
        return 0.0, 0.0
    f = SM_T5_HL_FILL
    if u < f:
        v = u / f
        ps, w = f * (v * v * v - 0.5 * v * v * v * v), v * v * (3.0 - 2.0 * v)
    else:
        ps, w = u - 0.5 * f, 1.0
    return c['hlE'] * (t5_softplus2(SM_T5_HL_RATE * (ps - SM_T5_HL_MID)) - SM_T5_HL_SP0) / SM_T5_HL_RATE, w


def t5_curve(e, c):
    """(T(e) - e, Soft Clip share, shoulder share, shoulder entry weight) for the curve c: Contrast, the
    Highlights shoulder, the 7 slots, Soft Clip."""
    # T - e is accumulated rather than T, so a large e does not cancel it away
    d = 0.0
    if c['conC'] != 0.0:
        d = c['conC'] * SM_T5_CON_R * math.tanh((e - c['conPivot']) / SM_T5_CON_R)
    hl = hw = 0.0
    if c['hlE'] != 0.0:
        hl, hw = t5_shoulder(e + d, c)
        d += hl
    for i in range(SM_T5_SLOTS):
        E = c['zoneE'][i]
        if E != 0.0:
            d += E * t5_zone(e + d, c['zoneEdge'][i], 1.0 if i < SM_T5_UP else -1.0, c['zoneK'][i], c['zoneFill'][i])
    tr = 0.0
    if c['roofOn']:
        tr = c['roofRenorm'] - t5_softplus2(SM_T5_ROOF_N * (e + d - c['roofStops'])) / SM_T5_ROOF_N
        d += tr
    return d, tr, hl, hw


def t5_zone_weight(e, z, p):
    """Nominal weight of zone z at e, in scene stops: zone Sat and the Zone false colour."""
    return t5_ramp((e - p['zNomEdge'][z]) * SM_T5_ZONE_DIR[z] * p['zNomInvF'][z])


def t5_gain(n, p):
    """(log2 G, e, tr, hl, hw) at norm n; e is the post-Blacks stop value the zones read, the rest as t5_curve."""
    lg = t5_blacks(n, p['blkA'], p['blkRenorm'])
    e = t5_log(n * 2.0 ** lg)
    d, tr, hl, hw = t5_curve(e, p)
    return lg + d, e, tr, hl, hw


def tone5(xyz, p):
    """sm_tone5: one scalar gain from the Rec.2020 norm, the path to white where Highlights compresses, then
    the colour stage."""
    n = t5_norm(dm.mul(dm.MATS[SM_T5_REF][1], xyz))
    if not n < 3.0e38:
        return list(xyz)
    lg, e, tr, hl, hw = t5_gain(n, p)
    g = 2.0 ** min(lg, 64.0)
    out = [v * g for v in xyz]
    if hl < 0.0:
        out = color.t5_hl_white(out, hl, p['hlAmount'] * hw, p['hlWhiteLin'], p['hlTaperSpace'], p.get('outGamut', 2))
    if p['colorOn'] or p['roofOn']:
        out = color.t5_color(out, e, tr, p)
    return out


def active(p):
    """The develop runs tone5 only when this holds; otherwise the stage is skipped."""
    return bool(p['toneOn'] or p['colorOn'] or p['roofOn'])


def false_color_zones(xyz, p):
    """fcMode 4: each zone tints by its nominal weight, overlaps mix, the rest is grey by e."""
    n = t5_norm(dm.mul(dm.MATS[SM_T5_REF][1], xyz))
    e = t5_log(n * 2.0 ** t5_blacks(n, p['blkA'], p['blkRenorm']))
    out, s = [0.0, 0.0, 0.0], 0.0
    for z in range(4):
        w = t5_zone_weight(e, z, p)
        s += w
        out = [o + w * t for o, t in zip(out, SM_FC_ZONE_TINT[z])]
    if s >= 1.0:
        return [o / s for o in out]
    mono = min(max((e + 6.0) / 11.5, 0.06), 0.92)
    return [o + (1.0 - s) * mono for o in out]


# ---------------------------------------------------------------- host policy

def contrast_map(t, con_c, con_pivot):
    return t + con_c * SM_T5_CON_R * math.tanh((t - con_pivot) / SM_T5_CON_R) if con_c != 0.0 else t


def hl_landing(target, roof_on, h):
    """sm_hl_landing: where the top must leave the shoulder to land on target, through the Soft Clip roof if on."""
    if not roof_on:
        return target
    n = SM_T5_ROOF_N
    ren = t5_softplus2(-n * h) / n
    want = min(target, h) - 0.1
    lo, hi = want, want + 8.0
    for _ in range(60):
        t = 0.5 * (lo + hi)
        if t + ren - t5_softplus2(n * (t - h)) / n < want:
            lo = t
        else:
            hi = t
    return 0.5 * (lo + hi)


def shoulder_policy(v, white, expo, con_c, con_pivot, roof_on=0, roof_h=2.5):
    """(hlE, hlStart, hlAmount, hlWhite) of Highlights v. -100 lands the recorded top, 6 stops over grey at the
    shot EI and taken through Contrast like the start, on white (at least MINPULL under the top, and through the
    Soft Clip roof when it is on); hlWhite is where it really lands. +100 is an expansion of slope <= 1.5."""
    a = abs(v) / 100.0
    a *= 1.5 - 0.5 * a
    start = contrast_map(SM_T5_HL_START, con_c, con_pivot)
    if v > 0.0:
        return a * SM_T5_HL_CPLUS, start, 0.0, white
    if v == 0.0:
        return 0.0, 0.0, 0.0, white
    top = contrast_map(SM_T5_HL_TOP + (math.log2(expo) if expo > 0.0 else 0.0), con_c, con_pivot)
    land = hl_landing(min(white, top - SM_T5_HL_MINPULL), roof_on, roof_h)
    D = t5_shoulder(top, {'hlE': 1.0, 'hlStart': start})[0]
    k = min(max(top - land, 0.0) / D, 1.0 - SM_T5_HL_SMIN) if D > 0.0 else 0.0
    return (-a * k, start, a, max(white, top - k * D)) if k > 0.0 else (0.0, 0.0, 0.0, white)


def zone_policy(con_c, con_pivot, nominal, hl_e=0.0, hl_start=0.0):
    """SMToneCurve without the roof. nominal: per slot (E, edge, falloff, s_max) in scene stops.

    Edge and falloff go through Contrast and the Highlights shoulder only, never
    through the other slots: that keeps every slot monotone in its own E (I13)."""
    c = {'conC': con_c, 'conPivot': con_pivot, 'hlE': hl_e, 'hlStart': hl_start if hl_e != 0.0 else 0.0,
         'zoneE': [0.0] * SM_T5_SLOTS, 'zoneEdge': [0.0] * SM_T5_SLOTS,
         'zoneK': [0.0] * SM_T5_SLOTS, 'zoneFill': [0.0] * SM_T5_SLOTS,
         'roofOn': 0, 'roofStops': 0.0, 'roofRenorm': 0.0}

    def to_slots(t):
        t = contrast_map(t, con_c, con_pivot)
        return t + t5_shoulder(t, c)[0]
    for i, (E, edge, f, smax) in enumerate(nominal):
        if E == 0.0:
            continue
        dirn = 1.0 if i < SM_T5_UP else -1.0
        e0 = to_slots(edge)
        fm = max(abs(to_slots(edge + dirn * f) - e0), SM_T5_F_MIN)
        lim = (1.0 - SM_T5_SMIN) if dirn * E < 0.0 else (smax - 1.0)
        c['zoneE'][i] = E
        c['zoneEdge'][i] = e0
        c['zoneK'][i] = min(SM_T5_RMAX / fm, lim / abs(E))
        c['zoneFill'][i] = 0.25 * fm
    return c


def controls_clamped(controls):
    """The panel values by OFX name, defaults filled in and clamped to the declared ranges."""
    unknown = set(controls) - set(CONTROLS)
    if unknown:
        raise KeyError('not a tone control: %s' % ', '.join(sorted(unknown)))
    return {n: min(max(float(controls.get(n, d)), lo), hi) for n, (lo, hi, d) in CONTROLS.items()}


def set_tone(controls, out_space=SM_T5_REF, convert=False, expo=1.0):
    """sm_set_tone: the tone fields of DevelopParams from the raw panel values; expo = chosen EI / shot EI."""
    v = controls_clamped(controls)
    b = v['toneBlacks'] / 100.0
    blk_a = 1.0 - 2.0 ** ((SM_T5_BLK_CRUSH if b < 0.0 else SM_T5_BLK_LIFT) * b)
    blk_renorm = 0.0
    if blk_a != 0.0:
        g18 = SM_T5_GREY - blk_a * SM_T5_BLK_PHI * (1.0 - math.exp(-SM_T5_GREY / SM_T5_BLK_PHI))
        blk_renorm = math.log2(SM_T5_GREY / g18)

    nominal = [(0.0, 0.0, 1.0, SM_T5_SMAX_CR)] * SM_T5_SLOTS
    for name, (slot, edge, f, stops) in SLIDER_SLOT.items():
        nominal[slot] = (stops * v[name] / 100.0, edge, f, SM_T5_SMAX_CR)
    for z, slot in zip(ZONES, ZONE_SLOT):
        nominal[slot] = (v['zone%sExp' % z], v['zone%sRange' % z], v['zone%sFalloff' % z], SM_T5_SMAX_ZONE)
    con_c = 2.0 ** (v['toneContrast'] / 100.0) - 1.0
    white = v['softClipLevel']
    hl_e, hl_start, hl_amount, hl_white = shoulder_policy(v['toneHighlights'], white, expo, con_c, v['zonePivot'],
                                                          int(v['softClip'] != 0.0), v['softClipLevel'])
    p = zone_policy(con_c, v['zonePivot'], nominal, hl_e, hl_start)

    p['roofPurity'] = p['roofLin'] = 0.0
    if v['softClip'] != 0.0:
        h = v['softClipLevel']
        ren = t5_softplus2(-SM_T5_ROOF_N * h) / SM_T5_ROOF_N
        p.update(roofOn=1, roofStops=h, roofRenorm=ren, roofPurity=2.0 ** (-v['softClipColor'] / 100.0),
                 roofLin=SM_T5_GREY * 2.0 ** (h + ren))
    p['hlAmount'] = hl_amount
    p['hlWhiteLin'] = SM_T5_GREY * 2.0 ** hl_white if hl_amount > 0.0 else 0.0
    p['hlTaperSpace'] = out_space if convert and out_space in (1, 2, 3, 4, 5) else 1

    p['blkA'], p['blkRenorm'] = blk_a, blk_renorm
    p['sat'], p['vib'] = v['toneSaturation'] / 100.0, v['toneVibrance'] / 100.0
    p['zSat'] = [v['zone%sSat' % z] / 100.0 for z in ZONES]
    p['zNomEdge'] = [v['zone%sRange' % z] for z in ZONES]
    p['zNomInvF'] = [1.0 / v['zone%sFalloff' % z] for z in ZONES]
    p['toneOn'] = int(blk_a != 0.0 or p['conC'] != 0.0 or p['hlE'] != 0.0 or any(E != 0.0 for E in p['zoneE']))
    p['colorOn'] = int(p['sat'] != 0.0 or p['vib'] != 0.0 or any(s != 0.0 for s in p['zSat']))
    p['refSpace'] = out_space if convert and out_space in (1, 2, 3, 4, 5) else SM_T5_REF
    return {k: p[k] for k in TONE_FIELDS}


# at the end: color imports this module back and needs everything above
from . import color  # noqa: E402
