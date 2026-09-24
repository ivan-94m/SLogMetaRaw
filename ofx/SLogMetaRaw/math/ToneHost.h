// SPDX-License-Identifier: GPL-3.0-or-later
// CPU only: the tone policy, from the raw panel values to DevelopParams, in double.
#pragma once
#include "Params.h"
#include "Tone.h"
#ifndef __METAL_VERSION__

// The panel as the colourist sees it: -100..100 sliders, zones in stops (Black, Shadow, Light, Specular).
struct SMToneControls {
    double contrast, highlights, shadows, whites, blacks, vibrance, saturation;
    double zonePivot, zoneExp[4], zoneSat[4], zoneRange[4], zoneFalloff[4];
    int softClip;
    double softClipLevel, softClipColor;
};

static const double SM_T5_SMIN = 0.35;             // flattest slope a compressive slot may reach
static const double SM_T5_SMAX_ZONE = 1.0 / 0.35;
static const double SM_T5_SMAX_CR = 2.0;           // steepest slope of the Camera Raw sliders
static const double SM_T5_F_MIN = 0.05;
static const double SM_T5_BLK_CRUSH = 3.0;         // Blacks -100 = -3 stops at black, +100 = +1
static const double SM_T5_BLK_LIFT = 1.0;
static const double SM_T5_HL_START = 0.0;         // the shoulder starts at grey: nothing below it moves
static const double SM_T5_HL_TOP = 6.0;           // S-Log3's recorded top at the shot EI (+6.06..+6.17 measured)
static const double SM_T5_HL_SMIN = 0.06;         // flattest slope of the shoulder
static const double SM_T5_HL_CPLUS = 0.5;         // Highlights +100: slope at most 1.5
static const double SM_T5_HL_MINPULL = 1.5;       // -100 always lowers the top this much, whatever Bianco says
static const int SM_T5_ZONE_SLOT[4] = { 4, 6, 3, 0 };

static inline SMToneControls sm_tone_defaults(void) {
    SMToneControls c = SMToneControls();
    const double range[4] = { -4.0, 1.0, -1.0, 4.0 }, falloff[4] = { 1.0, 2.0, 2.0, 1.0 };
    for (int z = 0; z < 4; ++z) { c.zoneRange[z] = range[z]; c.zoneFalloff[z] = falloff[z]; }
    c.softClipLevel = 2.5;
    return c;
}

static inline double sm_clampd(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }
static inline double sm_contrast_map(double t, double c, double pivot) {
    return c != 0.0 ? t + c * SM_T5_CON_R * tanh((t - pivot) / SM_T5_CON_R) : t;
}
static inline double sm_softplus2d(double y) { return (y > 0.0 ? y : 0.0) + log2(1.0 + exp2(-fabs(y))); }

// Where the top must leave the shoulder so that it lands on `target`: on target itself, or with Soft Clip on
// (roof at h) where the roof then brings it a tenth of a stop under target, not a third.
static inline double sm_hl_landing(double target, int roofOn, double h) {
    if (!roofOn) return target;
    const double n = SM_T5_ROOF_N, ren = sm_softplus2d(-n * h) / n, want = fmin(target, h) - 0.1;
    double lo = want, hi = want + 8.0;
    for (int i = 0; i < 60; ++i) {
        const double t = 0.5 * (lo + hi);
        if (t + ren - sm_softplus2d(n * (t - h)) / n < want) lo = t; else hi = t;
    }
    return 0.5 * (lo + hi);
}

// D(u) of the Highlights shoulder (sm_t5_shoulder) in double.
static inline double sm_shoulder_dd(double u) {
    if (!(u > 0.0)) return 0.0;
    const double f = SM_T5_HL_FILL, r = SM_T5_HL_RATE, m = SM_T5_HL_MID;
    double ps;
    if (u < f) {
        const double v = u / f;
        ps = f * (v * v * v - 0.5 * v * v * v * v);
    } else {
        ps = u - 0.5 * f;
    }
    return (sm_softplus2d(r * (ps - m)) - sm_softplus2d(-r * m)) / r;
}

// nominal[slot] = { E, edge, falloff, s_max } in scene stops. Edge and falloff go through Contrast and
// the Highlights shoulder only, never through the other slots: that keeps every slot monotone in its own E.
static inline void sm_zone_policy(double conC, double conPivot, const double nominal[SM_T5_SLOTS][4], SMToneCurve* c,
                                  double hlE = 0.0, double hlStart = 0.0) {
    *c = SMToneCurve();
    c->conC = (float)conC;
    c->conPivot = (float)conPivot;
    if (hlE != 0.0) {
        c->hlE = (float)hlE;
        c->hlStart = (float)hlStart;
    }
    for (int i = 0; i < SM_T5_SLOTS; ++i) {
        const double E = nominal[i][0], edge = nominal[i][1], f = nominal[i][2], smax = nominal[i][3];
        if (E == 0.0) continue;
        const double dir = i < SM_T5_UP ? 1.0 : -1.0;
        double e0 = sm_contrast_map(edge, conC, conPivot), e1 = sm_contrast_map(edge + dir * f, conC, conPivot);
        e0 += hlE * sm_shoulder_dd(e0 - hlStart);
        e1 += hlE * sm_shoulder_dd(e1 - hlStart);
        double fm = fabs(e1 - e0);
        if (fm < SM_T5_F_MIN) fm = SM_T5_F_MIN;
        const double lim = dir * E < 0.0 ? 1.0 - SM_T5_SMIN : smax - 1.0;
        const double k1 = (double)SM_T5_RMAX / fm, k2 = lim / fabs(E);
        c->zoneE[i] = (float)E;
        c->zoneEdge[i] = (float)e0;
        c->zoneK[i] = (float)(k1 < k2 ? k1 : k2);
        c->zoneFill[i] = (float)(0.25 * fm);
    }
}

// refSpace: the output gamut when the node converts to 709 / 2020 / P3, else Rec.2020.
// expo: chosen EI / shot EI, which moves the recorded top Highlights -100 lands on Bianco (softClipLevel).
static inline void sm_set_tone(DevelopParams* p, const SMToneControls* in, int outSpace, int convert,
                               double expo = 1.0) {
    SMToneControls v = *in;
    v.contrast = sm_clampd(v.contrast, -100, 100); v.highlights = sm_clampd(v.highlights, -100, 100);
    v.shadows = sm_clampd(v.shadows, -100, 100); v.whites = sm_clampd(v.whites, -100, 100);
    v.blacks = sm_clampd(v.blacks, -100, 100); v.vibrance = sm_clampd(v.vibrance, -100, 100);
    v.saturation = sm_clampd(v.saturation, -100, 100); v.zonePivot = sm_clampd(v.zonePivot, -4, 4);
    for (int z = 0; z < 4; ++z) {
        v.zoneExp[z] = sm_clampd(v.zoneExp[z], -6, 6);
        v.zoneSat[z] = sm_clampd(v.zoneSat[z], -100, 100);
        v.zoneRange[z] = sm_clampd(v.zoneRange[z], -10, 10);
        v.zoneFalloff[z] = sm_clampd(v.zoneFalloff[z], 0.5, 6);
    }
    v.softClipLevel = sm_clampd(v.softClipLevel, 1, 10);
    v.softClipColor = sm_clampd(v.softClipColor, -100, 100);

    const double b = v.blacks / 100.0;
    const double blkA = 1.0 - exp2((b < 0.0 ? SM_T5_BLK_CRUSH : SM_T5_BLK_LIFT) * b);
    double blkRenorm = 0.0;
    if (blkA != 0.0) {
        const double grey = SM_T5_GREY, phi = SM_T5_BLK_PHI;
        blkRenorm = log2(grey / (grey - blkA * phi * (1.0 - exp(-grey / phi))));
    }

    double nominal[SM_T5_SLOTS][4] = {};
    const double sliders[2][5] = { { 1, 3.5, 1.0, 1.0, v.whites },
                                   { 5, -1.0, 2.0, 2.0, v.shadows } };   // slot, edge, falloff, stops at 100, value
    for (int s = 0; s < 2; ++s) {
        double* n = nominal[(int)sliders[s][0]];
        n[0] = sliders[s][3] * sliders[s][4] / 100.0; n[1] = sliders[s][1]; n[2] = sliders[s][2]; n[3] = SM_T5_SMAX_CR;
    }
    for (int z = 0; z < 4; ++z) {
        double* n = nominal[SM_T5_ZONE_SLOT[z]];
        n[0] = v.zoneExp[z]; n[1] = v.zoneRange[z]; n[2] = v.zoneFalloff[z]; n[3] = SM_T5_SMAX_ZONE;
    }
    const double conC = exp2(v.contrast / 100.0) - 1.0, white = v.softClipLevel;

    // Highlights: the shoulder, eased. At -100 the recorded top, taken through Contrast as the start is, lands on
    // Bianco (at least MINPULL under the top), unless the slope floor stops it first (Bianco under ~2.3).
    double a = fabs(v.highlights) / 100.0, hlE = 0.0, hlAmount = 0.0, hlWhite = white;
    a *= 1.5 - 0.5 * a;
    const double hlStart = sm_contrast_map(SM_T5_HL_START, conC, v.zonePivot);
    if (v.highlights > 0.0) {
        hlE = a * SM_T5_HL_CPLUS;
    } else if (v.highlights < 0.0) {
        const double top = sm_contrast_map(SM_T5_HL_TOP + (expo > 0.0 ? log2(expo) : 0.0), conC, v.zonePivot);
        const double land = sm_hl_landing(fmin(white, top - SM_T5_HL_MINPULL), v.softClip, v.softClipLevel);
        const double D = sm_shoulder_dd(top - hlStart);
        const double k = D > 0.0 ? fmin(fmax(top - land, 0.0) / D, 1.0 - SM_T5_HL_SMIN) : 0.0;
        if (k > 0.0) {
            hlE = -a * k;
            hlAmount = a;
            hlWhite = fmax(white, top - k * D);   // the taper sits where the top really lands
        }
    }
    sm_zone_policy(conC, v.zonePivot, nominal, &p->curve, hlE, hlStart);

    p->roofPurity = p->roofLin = 0.0f;
    if (v.softClip != 0) {
        const double h = v.softClipLevel, ren = sm_softplus2d(-(double)SM_T5_ROOF_N * h) / SM_T5_ROOF_N;
        p->curve.roofOn = 1;
        p->curve.roofStops = (float)h;
        p->curve.roofRenorm = (float)ren;
        p->roofPurity = (float)exp2(-v.softClipColor / 100.0);
        p->roofLin = (float)(SM_T5_GREY * exp2(h + ren));
    }
    p->hlAmount = (float)hlAmount;
    p->hlWhiteLin = hlAmount > 0.0 ? (float)(SM_T5_GREY * exp2(hlWhite)) : 0.0f;
    p->hlTaperSpace = (convert && outSpace >= 1 && outSpace <= 5) ? outSpace : 1;
    p->blkA = (float)blkA;
    p->blkRenorm = (float)blkRenorm;
    p->sat = (float)(v.saturation / 100.0);
    p->vib = (float)(v.vibrance / 100.0);
    int zoneOn = 0, zoneSatOn = 0;
    for (int z = 0; z < 4; ++z) {
        p->zSat[z] = (float)(v.zoneSat[z] / 100.0);
        p->zNomEdge[z] = (float)v.zoneRange[z];
        p->zNomInvF[z] = (float)(1.0 / v.zoneFalloff[z]);
        zoneSatOn |= p->zSat[z] != 0.0f;
    }
    for (int i = 0; i < SM_T5_SLOTS; ++i) zoneOn |= p->curve.zoneE[i] != 0.0f;
    p->toneOn = (blkA != 0.0 || p->curve.conC != 0.0f || p->curve.hlE != 0.0f || zoneOn) ? 1 : 0;
    p->colorOn = (p->sat != 0.0f || p->vib != 0.0f || zoneSatOn) ? 1 : 0;
    p->refSpace = (convert && outSpace >= 1 && outSpace <= 5) ? outSpace : SM_T5_REF;
}
#endif
