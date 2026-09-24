// SPDX-License-Identifier: GPL-3.0-or-later
// Colour stage of the v5 tone engine: XYZ' = Y*W + m*(XYZ - Y*W), so Y stays and the chroma
// scales by m. Channel limits are read in the gamut R, which depends on the output only.
// Highlights' path to white, before it, scales the chroma in Oklab instead: a straight line in linear
// light bends hue (orange to salmon, blue to lavender).
#pragma once
#include "Tone.h"

SM_FN float sm_t5_p4(float x) { float x2 = x * x; return x2 * x2; }

// Saturation, Vibrance (skin protected) and zone Sat, softly limited where a channel of R would go negative.
SM_FN float sm_t5_sat(SMf3 xyz, float e, SM_CREF(DevelopParams) p) {
    float d = xyz.x + 15.0f * xyz.y + 3.0f * xyz.z;
    float sn = 0.0f, skin = 0.0f;
    if (d > 1e-30f) {
        float du = 4.0f * xyz.x / d - SM_T5_UW, dv = 9.0f * xyz.y / d - SM_T5_VW;
        float s = SM_SQRT(du * du + dv * dv);
        sn = s / (s + SM_T5_SAT_HALF);
        if (p.vib > 0.0f && s > 1e-12f) {
            float dh = SM_ABS(SM_ATAN2(dv, du) - SM_T5_SKIN_HUE);
            dh = SM_MIN(dh, 6.283185307f - dh);
            skin = sm_t5_ramp((SM_T5_SKIN_ZERO - dh) / (SM_T5_SKIN_ZERO - SM_T5_SKIN_FULL));
        }
    }
    float m = (1.0f + p.sat) * (1.0f + p.vib * (1.0f - sn) * (p.vib > 0.0f ? 1.0f - SM_T5_SKIN_PROTECT * skin : 1.0f));
    for (int z = 0; z < 4; ++z) m *= 1.0f + p.zSat[z] * sm_t5_zone_weight(e, z, p);
    if (m <= 1.0f) return m;
    if (xyz.y <= 0.0f) return 1.0f;
    SMf3 c = sm_from_xyz(xyz, p.refSpace);
    float acc = 0.0f;
    if (c.x < xyz.y) acc += sm_t5_p4((xyz.y - c.x) / xyz.y);
    if (c.y < xyz.y) acc += sm_t5_p4((xyz.y - c.y) / xyz.y);
    if (c.z < xyz.y) acc += sm_t5_p4((xyz.y - c.z) / xyz.y);
    if (acc <= 0.0f) return m;
    float rho = SM_MAX(SM_POW(acc, -1.0f / SM_T5_GAMUT_P) - 1.0f, 0.0f);
    float x = m - 1.0f;
    return 1.0f + (rho > 0.0f ? x / SM_POW(1.0f + sm_t5_p4(x / rho), 1.0f / SM_T5_GAMUT_P) : 0.0f);
}

// m with every channel of the gamut `space` kept softly below h; 0 once Y reaches h (1 + soft).
SM_FN float sm_t5_limit(SMf3 xyz, float m, float h, int space, float soft) {
    float y = xyz.y, room = h * (1.0f + soft) - y;
    if (room <= 0.0f) return 0.0f;
    SMf3 c = sm_from_xyz(xyz, space);
    float acc = 0.0f;
    if (c.x > y) acc += sm_t5_p4((c.x - y) / room);
    if (c.y > y) acc += sm_t5_p4((c.y - y) / room);
    if (c.z > y) acc += sm_t5_p4((c.z - y) / room);
    if (acc > 0.0f && m > 0.0f)
        m /= SM_POW(1.0f + sm_t5_p4(m * SM_POW(acc, 1.0f / SM_T5_GAMUT_P)), 1.0f / SM_T5_GAMUT_P);
    return m;
}

// After the Soft Clip: purity falls where the roof pulls down, and every channel of R stays below the roof.
SM_FN float sm_t5_roof(SMf3 xyz, float m, float tr, SM_CREF(DevelopParams) p) {
    if (tr < 0.0f) {
        float k = SM_T5_ROOF_K * (1.0f + SM_T5_ROOF_GROW * (1.0f - SM_EXP2(tr))) * p.roofPurity;
        m *= SM_EXP2(k * tr);
    }
    return sm_t5_limit(xyz, m, p.roofLin, p.refSpace, 0.0f);
}

SM_FN SMf3 sm_t5_chroma(SMf3 xyz, float m) {
    return smf3(xyz.y * SM_T5_WX + m * (xyz.x - xyz.y * SM_T5_WX), xyz.y,
                xyz.y * SM_T5_WZ + m * (xyz.z - xyz.y * SM_T5_WZ));
}

// Oklab (Ottosson 2020) from XYZ D65: M1, M2, M2^-1, M1^-1.
SM_CONST float SM_OKLAB[36] = {
    0.8189330101f, 0.3618667424f, -0.1288597137f, 0.0329845436f, 0.9293118715f, 0.0361456387f,
    0.0482003018f, 0.2643662691f, 0.6338517070f,
    0.2104542553f, 0.7936177850f, -0.0040720468f, 1.9779984951f, -2.4285922050f, 0.4505937099f,
    0.0259040371f, 0.7827717662f, -0.8086757660f,
    1.0f, 0.3963377774f, 0.2158037573f, 1.0f, -0.1055613458f, -0.0638541728f, 1.0f, -0.0894841775f, -1.2914855480f,
    1.2270138511f, -0.5577999807f, 0.2812561490f, -0.0405801784f, 1.1122568696f, -0.0716766787f,
    -0.0763812845f, -0.4214819784f, 1.5861632204f };

// Metal has no cbrt: exp2/log2 (precise on both sides) and one Newton step.
SM_FN float sm_cbrt(float x) {
    float a = SM_ABS(x);
    if (!(a > 1e-30f)) return 0.0f;
    float r = SM_EXP2(SM_LOG2(a) / 3.0f);
    r -= (r * r * r - a) / (3.0f * r * r);
    return x < 0.0f ? -r : r;
}

// Chroma times m at constant Oklab hue and lightness.
SM_FN SMf3 sm_oklab_chroma(SMf3 xyz, float m) {
    SMf3 l = sm_mul(SM_OKLAB, 0, xyz);
    SMf3 lab = sm_mul(SM_OKLAB, 9, smf3(sm_cbrt(l.x), sm_cbrt(l.y), sm_cbrt(l.z)));
    l = sm_mul(SM_OKLAB, 18, smf3(lab.x, m * lab.y, m * lab.z));
    return sm_mul(SM_OKLAB, 27, smf3(l.x * l.x * l.x, l.y * l.y * l.y, l.z * l.z * l.z));
}

// Where Highlights compresses (hl < 0): the path to white, chroma 2^(KAPPA hl) at constant hue, lowered further
// by w where a channel of `space` would pass the white (the display-white taper). Both nodes use it.
// Oklab only holds for real colours: past the spectral locus (S-Gamut3.Cine reaches there on LEDs and neon) its
// cones go negative and the path would too, so there it fades into the straight line in linear light.
// The share of b over a that keeps the channel >= 0, with a 2% margin: landing on exactly 0 would leave float
// noise that a power curve turns into visible code-value differences between CPU and GPU.
SM_FN float sm_t5_keep_positive(float t, float a, float b) {
    a = SM_MAX(a, 0.0f);
    return b < 0.0f ? SM_MIN(t, 0.98f * a / (a - b)) : t;
}
SM_FN SMf3 sm_t5_hl_white(SMf3 xyz, float hl, float w, float whiteLin, int space, int outSpace) {
    float m = SM_EXP2(SM_T5_HL_KAPPA * hl);
    if (w > 0.0f)
        m *= 1.0f - w * (1.0f - sm_t5_limit(sm_t5_chroma(xyz, m), 1.0f, whiteLin, space, SM_T5_HL_SOFT));
    // the straight line goes to the power norm, not to Y: a deep blue LED in S-Gamut3.Cine has negative Y
    SMf3 c = sm_from_xyz(xyz, SM_T5_REF);
    float N = sm_t5_norm(c);
    SMf3 lin = sm_to_xyz(smf3(N + m * (c.x - N), N + m * (c.y - N), N + m * (c.z - N)), SM_T5_REF);
    c = sm_mul(SM_OKLAB, 0, xyz);
    float hi = SM_MAX(c.x, SM_MAX(c.y, c.z)), lo = SM_MIN(c.x, SM_MIN(c.y, c.z));
    float t = hi > 0.0f ? sm_t5_ramp(lo / (0.1f * hi)) : 0.0f;
    if (t <= 0.0f) return lin;
    SMf3 ok = sm_oklab_chroma(xyz, m);
    // on the edge of the gamut the node writes, the curved path can step outside it: the straight line cannot
    SMf3 a = sm_from_xyz(lin, outSpace), b = sm_from_xyz(ok, outSpace);
    t = sm_t5_keep_positive(sm_t5_keep_positive(sm_t5_keep_positive(t, a.x, b.x), a.y, b.y), a.z, b.z);
    return smf3(lin.x + t * (ok.x - lin.x), lin.y + t * (ok.y - lin.y), lin.z + t * (ok.z - lin.z));
}

SM_FN SMf3 sm_t5_color(SMf3 xyz, float e, float tr, SM_CREF(DevelopParams) p) {
    float m = p.colorOn != 0 ? sm_t5_sat(xyz, e, p) : 1.0f;
    if (p.curve.roofOn != 0) m = sm_t5_roof(xyz, m, tr, p);
    return sm_t5_chroma(xyz, m);
}

// The whole stage on XYZ after exposure and white balance.
SM_FN SMf3 sm_tone5(SMf3 xyz, SM_CREF(DevelopParams) p) {
    float n = sm_t5_norm(sm_from_xyz(xyz, SM_T5_REF));
    if (!(n < 3.0e38f)) return xyz;   // NaN and Inf pass through: they must not turn into NaN in all three
    float lg = sm_t5_blacks(n, p.blkA, p.blkRenorm);
    float e = sm_t5_log(n * SM_EXP2(lg));
    SMToneOut o = sm_t5_curve(e, p.curve);
    float g = SM_EXP2(SM_MIN(lg + o.d, 64.0f));
    SMf3 out = smf3(xyz.x * g, xyz.y * g, xyz.z * g);
    if (o.hl < 0.0f)
        out = sm_t5_hl_white(out, o.hl, p.hlAmount * o.hw, p.hlWhiteLin, p.hlTaperSpace,
                             p.convert != 0 ? p.outSpace : p.nodeSpace);
    if (p.colorOn != 0 || p.curve.roofOn != 0) out = sm_t5_color(out, e, o.tr, p);
    return out;
}
