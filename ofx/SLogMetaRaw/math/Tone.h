// SPDX-License-Identifier: GPL-3.0-or-later
// v5 tone engine: one scalar gain per pixel from a norm, T in stops composed of monotone maps
// (docs/TONE_MAPPING.md). Reference: tests/model/tone.py.
#pragma once
#include "Params.h"
#include "Gamut.h"

SM_CONST float SM_T5_GREY = 0.18f;
SM_CONST float SM_T5_EPS = 2.746582031e-06f;     // grey * 2^-16: the soft floor of the stop scale
SM_CONST float SM_T5_DELTA = 0.25f;
SM_CONST float SM_T5_RMAX = 1.333333333f;
SM_CONST float SM_T5_W = 0.1666666667f;
SM_CONST float SM_T5_CON_R = 4.0f;
SM_CONST float SM_T5_BLK_PHI = 0.005625f;        // the Blacks veil scale, 5 stops under grey
SM_CONST float SM_T5_ROOF_N = 3.0f;
SM_CONST float SM_T5_ROOF_K = 0.5f;
SM_CONST float SM_T5_ROOF_GROW = 1.0f;
SM_CONST float SM_T5_SAT_HALF = 0.05f;
SM_CONST float SM_T5_SKIN_HUE = 0.5759586532f;   // 33 degrees in u'v'
SM_CONST float SM_T5_SKIN_FULL = 0.1745329252f;
SM_CONST float SM_T5_SKIN_ZERO = 0.5235987756f;
SM_CONST float SM_T5_SKIN_PROTECT = 0.7f;
SM_CONST float SM_T5_GAMUT_P = 4.0f;
// D65 as the matrices have it (xy 0.3127, 0.3290): RGB (Y, Y, Y) is exactly Y*W in every gamut
SM_CONST float SM_T5_WX = 0.9504559271f;
SM_CONST float SM_T5_WZ = 1.089057751f;
SM_CONST float SM_T5_UW = 0.1978300066f;
SM_CONST float SM_T5_VW = 0.4683199949f;
SM_CONST float SM_T5_ZONE_DIR[4] = { -1.0f, -1.0f, 1.0f, 1.0f };
// Highlights shoulder D(u) = [softplus2(RATE (psi(u) - MID)) - SP0] / RATE, psi the C2 entry of width FILL
SM_CONST float SM_T5_HL_FILL = 2.0f;
SM_CONST float SM_T5_HL_RATE = 1.4f;
SM_CONST float SM_T5_HL_MID = 0.9f;
SM_CONST float SM_T5_HL_SP0 = 0.5033934755f;    // softplus2(-RATE * MID): D(0) = 0
SM_CONST float SM_T5_HL_KAPPA = 0.12f;          // path to white: chroma 2^(KAPPA * hl), in Oklab
SM_CONST float SM_T5_HL_SOFT = 0.25f;           // the white taper's limiter eases off: a 33-point LUT can follow it
#define SM_T5_REF 2   // Rec.2020: the norm is taken there, whatever the node works in

// T - e, the Soft Clip share of it, the Highlights shoulder share and the weight 0..1 of its entry
struct SMToneOut { float d; float tr; float hl; float hw; };

// Power norm sum|c|^3 / sum c^2: norm(x, x, x) = x; divided by max|c| first so no sum overflows.
SM_FN float sm_t5_norm(SMf3 c) {
    float mx = SM_MAX(SM_ABS(c.x), SM_MAX(SM_ABS(c.y), SM_ABS(c.z)));
    if (!(mx > 1e-30f)) return 0.0f;
    float x = c.x / mx, y = c.y / mx, z = c.z / mx;
    return mx * (SM_ABS(x) * x * x + SM_ABS(y) * y * y + SM_ABS(z) * z * z) / (x * x + y * y + z * z);
}

// log2(sqrt(n^2 + eps^2) / grey): the gain stays finite at black.
SM_FN float sm_t5_log(float n) {
    float a = SM_MAX(n, SM_T5_EPS), b = SM_MIN(n, SM_T5_EPS), q = b / a;
    return SM_LOG2(a / SM_T5_GREY) + 0.5f * SM_LOG2(1.0f + q * q);
}

// C2 ramp 0 -> 1 over [0, 1], linear at slope RMAX in the middle.
SM_FN float sm_t5_ramp(float u) {
    if (u <= 0.0f) return 0.0f;
    if (u >= 1.0f) return 1.0f;
    if (u < SM_T5_DELTA) {
        float t = u / SM_T5_DELTA;
        return SM_T5_RMAX * SM_T5_DELTA * (t * t * t - 0.5f * t * t * t * t);
    }
    if (u > 1.0f - SM_T5_DELTA) {
        float t = (1.0f - u) / SM_T5_DELTA;
        return 1.0f - SM_T5_RMAX * SM_T5_DELTA * (t * t * t - 0.5f * t * t * t * t);
    }
    return SM_T5_RMAX * (u - 0.5f * SM_T5_DELTA);
}

// (1 - e^-x) / x through tanh: the direct form cancels in float32 near 0.
SM_FN float sm_t5_h(float x) {
    if (x < 1e-4f) return 1.0f - 0.5f * x + x * x / 6.0f;
    return SM_TANH(0.5f * x) * (1.0f + SM_EXP(-x)) / x;
}

SM_FN float sm_t5_blacks(float n, float a, float renorm) {
    if (a == 0.0f) return 0.0f;
    float w = n > SM_T5_GREY ? 1.0f - sm_t5_ramp(0.5f * SM_LOG2(n / SM_T5_GREY)) : 1.0f;
    return SM_LOG2(1.0f - a * sm_t5_h(n / SM_T5_BLK_PHI)) + w * renorm;
}

// rho of one slot at t: 0 on the still side, 1 past the band; the slot moves t by E * rho.
SM_FN float sm_t5_zone(float t, float edge, float dir, float k, float fill) {
    float d = (t - edge) * dir;
    if (d <= 0.0f) return 0.0f;
    float psi;
    if (d < fill) {
        float u = d / fill;
        psi = fill * (u * u * u - 0.5f * u * u * u * u);
    } else {
        psi = d - 0.5f * fill;
    }
    float x = k * psi;
    if (x <= 1.0f - SM_T5_W) return x;
    if (x >= 1.0f + SM_T5_W) return 1.0f;
    float v = (x - (1.0f - SM_T5_W)) / (2.0f * SM_T5_W);
    return x - 2.0f * SM_T5_W * (v * v * v - 0.5f * v * v * v * v);
}

SM_FN float sm_t5_softplus2(float y) {
    return SM_MAX(y, 0.0f) + SM_LOG2(1.0f + SM_EXP2(-SM_ABS(y)));
}

// The Highlights shoulder at t: d = T - t = E * D(t - start), exactly 0 at and below the start; w = psi' of its
// C2 entry, the weight the colour stage comes in with; s = E * D', the slope minus 1 (Local Highlights reads it).
struct SMShoulder { float d; float w; float s; };
SM_FN SMShoulder sm_t5_shoulder_at(float t, float E, float start) {
    SMShoulder o;
    o.d = 0.0f;
    o.w = 0.0f;
    o.s = 0.0f;
    float u = t - start;
    if (!(u > 0.0f) || E == 0.0f) return o;
    float ps;
    if (u < SM_T5_HL_FILL) {
        float v = u / SM_T5_HL_FILL;
        ps = SM_T5_HL_FILL * (v * v * v - 0.5f * v * v * v * v);
        o.w = v * v * (3.0f - 2.0f * v);
    } else {
        ps = u - 0.5f * SM_T5_HL_FILL;
        o.w = 1.0f;
    }
    float y = SM_T5_HL_RATE * (ps - SM_T5_HL_MID);
    float q = SM_EXP2(-SM_ABS(y));
    o.d = E * (sm_t5_softplus2(y) - SM_T5_HL_SP0) / SM_T5_HL_RATE;
    o.s = E * (y >= 0.0f ? 1.0f / (1.0f + q) : q / (1.0f + q)) * o.w;
    return o;
}
SM_FN SMShoulder sm_t5_shoulder(float t, SM_CREF(SMToneCurve) c) {
    return sm_t5_shoulder_at(t, c.hlE, c.hlStart);
}

SM_FN SMToneOut sm_t5_curve(float e, SM_CREF(SMToneCurve) c) {
    SMToneOut o;
    o.d = 0.0f;   // T - e accumulated, not T: a large e must not cancel it away
    if (c.conC != 0.0f) o.d = c.conC * SM_T5_CON_R * SM_TANH((e - c.conPivot) / SM_T5_CON_R);
    o.hl = 0.0f;
    o.hw = 0.0f;
    if (c.hlE != 0.0f) {
        SMShoulder s = sm_t5_shoulder(e + o.d, c);
        o.hl = s.d;
        o.hw = s.w;
        o.d += s.d;
    }
    for (int i = 0; i < SM_T5_SLOTS; ++i)
        if (c.zoneE[i] != 0.0f)
            o.d += c.zoneE[i] * sm_t5_zone(e + o.d, c.zoneEdge[i], i < SM_T5_UP ? 1.0f : -1.0f, c.zoneK[i], c.zoneFill[i]);
    o.tr = 0.0f;
    if (c.roofOn != 0) {
        o.tr = c.roofRenorm - sm_t5_softplus2(SM_T5_ROOF_N * (e + o.d - c.roofStops)) / SM_T5_ROOF_N;
        o.d += o.tr;
    }
    return o;
}

// Nominal weight of zone z at e (scene stops): zone Sat and the Zone false colour.
SM_FN float sm_t5_zone_weight(float e, int z, SM_CREF(DevelopParams) p) {
    return sm_t5_ramp((e - p.zNomEdge[z]) * SM_T5_ZONE_DIR[z] * p.zNomInvF[z]);
}
