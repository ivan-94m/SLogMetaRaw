// SPDX-License-Identifier: GPL-3.0-or-later
// CPU only: the Detail node's parameters from the panel and the frame size, in double.
#pragma once
#include "Detail.h"
#include "HostOnly.h"
#include "ToneHost.h"
#ifndef __METAL_VERSION__

struct SMDetailControls {
    double localContrast, localHighlights, localShadows, texture, clarity, dehaze;
    double zonePivot, zoneExp[4], zoneRange[4], zoneFalloff[4];
    double preserveDetail, detailRadius, edgeThreshold, noiseThreshold, clarityCenter, hazeLevel, hazeWarmth;
    double localWhite;
    int viewGain, viewBase;
};

static const int SM_DT_GRID_BASE = 540;   // working height: H / s in [0.707, 1.414) * 540
static const double SM_DT_HL_START = -0.5;  // Local Highlights starts half a stop under grey: the detail is kept there

static inline SMDetailControls sm_detail_defaults(void) {
    SMDetailControls c = SMDetailControls();
    const double range[4] = { -4.0, 1.0, -1.0, 4.0 }, falloff[4] = { 1.0, 2.0, 2.0, 1.0 };
    for (int z = 0; z < 4; ++z) { c.zoneRange[z] = range[z]; c.zoneFalloff[z] = falloff[z]; }
    c.preserveDetail = 100.0;
    c.detailRadius = 4.0;
    c.edgeThreshold = 0.5;
    c.noiseThreshold = 0.04;
    c.hazeLevel = 2.0;
    c.localWhite = 2.5;
    return c;
}

// n with 2 H^2 >= base^2 4^n, integers only: the grid does not jump between proxy and full size.
static inline int dt_grid_scale(int H, int base) {
    int n = 0;
    while (2.0 * H * H >= (double)base * base * (double)(1LL << (2 * (n + 1)))) ++n;
    return n;
}

static inline int dt_gauss_half(double sigma, float* half, int cap) {
    int R = (int)ceil(3.0 * sigma);
    if (R > cap - 1) R = cap - 1;
    for (int k = 0; k <= R; ++k) half[k] = (float)exp(-k * k / (2.0 * sigma * sigma));
    return R + 1;
}

// The veil in the input gamut: a neutral seen under a light of 10^6 / (153.8 + 0.8 v) K, norm 1.
static inline void dt_veil(double warmth, int space, double out[3]) {
    double w[3], w0[3], ls[3], l0[3], lms[3], d65[3] = { 0.95046, 1.0, 1.08906 }, xyz[3];
    sm_white_xyz(1e6 / (153.8 + 0.8 * warmth), 0.0, w);
    sm_white_xyz(1e6 / 153.8, 0.0, w0);
    sm_bradford(w, ls, 0);
    sm_bradford(w0, l0, 0);
    sm_bradford(d65, lms, 0);
    for (int i = 0; i < 3; ++i) lms[i] *= ls[i] / l0[i];
    sm_bradford(lms, xyz, 1);
    const float* m = SM_XYZ_TO_RGB + space * 9;
    for (int i = 0; i < 3; ++i) {
        const double c = m[i * 3] * xyz[0] + m[i * 3 + 1] * xyz[1] + m[i * 3 + 2] * xyz[2];
        out[i] = c > 0.02 ? c : 0.02;
    }
    const double mx = fmax(out[0], fmax(out[1], out[2]));
    double x = out[0] / mx, y = out[1] / mx, z = out[2] / mx;
    double n = mx * (x * x * x + y * y * y + z * z * z) / (x * x + y * y + z * z);
    if (n < 1e-3) n = 1e-3;
    for (int i = 0; i < 3; ++i) out[i] /= n;
}

// href: the height the radii are relative to (the frame height; tests pass another to scale a small image).
static inline void dt_prepare(DetailParams* p, int W, int H, double href, double par, int space, int gamma,
                              const SMDetailControls* in, int base) {
    SMDetailControls v = *in;
    v.localContrast = sm_clampd(v.localContrast, -100, 50);
    v.localHighlights = sm_clampd(v.localHighlights, -100, 100);
    v.localShadows = sm_clampd(v.localShadows, -100, 100);
    v.texture = sm_clampd(v.texture, -100, 100);
    v.clarity = sm_clampd(v.clarity, -100, 100);
    v.dehaze = sm_clampd(v.dehaze, -100, 100);
    v.zonePivot = sm_clampd(v.zonePivot, -4, 4);
    for (int z = 0; z < 4; ++z) {
        v.zoneExp[z] = sm_clampd(v.zoneExp[z], -6, 6);
        v.zoneRange[z] = sm_clampd(v.zoneRange[z], -10, 10);
        v.zoneFalloff[z] = sm_clampd(v.zoneFalloff[z], 0.5, 6);
    }
    v.preserveDetail = sm_clampd(v.preserveDetail, 0, 100);
    v.detailRadius = sm_clampd(v.detailRadius, 1, 8);
    v.edgeThreshold = sm_clampd(v.edgeThreshold, 0.25, 1.0);
    v.noiseThreshold = sm_clampd(v.noiseThreshold, 0.0, 0.15);
    v.clarityCenter = sm_clampd(v.clarityCenter, -3, 3);
    v.hazeLevel = sm_clampd(v.hazeLevel, -2, 6);
    v.hazeWarmth = sm_clampd(v.hazeWarmth, -100, 100);
    v.localWhite = sm_clampd(v.localWhite, 1, 10);

    *p = DetailParams();
    p->W = W;
    p->H = H;
    p->space = space;
    p->gamma = gamma;
    const int n = dt_grid_scale(H, base);
    p->s = 1 << n;
    p->w = (W + p->s - 1) / p->s;
    p->h = (H + p->s - 1) / p->s;
    const double gh = href / p->s;
    const double sigma1 = fmax(0.5, 0.0005 * href), sigma2 = 0.004 * href;
    int nt = sigma2 > 0.0 ? (int)floor(log2(sigma2 / 4.0)) : 0;
    nt = nt < 0 ? 0 : (nt > n ? n : nt);
    p->st = 1 << nt;
    p->wt = (W + p->st - 1) / p->st;
    p->ht = (H + p->st - 1) / p->st;
    const double tentVar = p->st >= 2 ? (2.0 * p->st * p->st + 1.0) / 12.0 : 0.0;
    const double sigmaT = sqrt(fmax(sigma2 * sigma2 - tentVar, 0.25)) / p->st;
    const double radii[5] = { v.detailRadius / 100.0 * gh, 0.005 * gh, 0.025 * gh, 0.005 * gh, 0.02 * gh };
    float* const rx[5] = { &p->rBx, &p->r2x, &p->r3x, &p->rpx, &p->rtx };
    float* const ry[5] = { &p->rBy, &p->r2y, &p->r3y, &p->rpy, &p->rty };
    for (int i = 0; i < 5; ++i) { *rx[i] = (float)(radii[i] / par); *ry[i] = (float)radii[i]; }
    p->eps = (float)((v.edgeThreshold / 2.0) * (v.edgeThreshold / 2.0));
    p->epsT = 0.01f;
    p->nG = dt_gauss_half(1.0, p->gG, SM_DT_GG);
    p->n1 = dt_gauss_half(sigma1, p->g1, SM_DT_G1);
    p->nT = dt_gauss_half(sigmaT, p->gT, SM_DT_GT);

    double nominal[SM_T5_SLOTS][4] = {};
    for (int i = 0; i < SM_T5_SLOTS; ++i) { nominal[i][2] = 1.0; nominal[i][3] = SM_T5_SMAX_CR; }
    const double sh[4] = { 0.02 * v.localShadows, 0.0, 1.5, SM_T5_SMAX_CR };
    for (int k = 0; k < 4; ++k) nominal[5][k] = sh[k];
    for (int z = 0; z < 4; ++z) {
        double* s = nominal[SM_T5_ZONE_SLOT[z]];
        s[0] = v.zoneExp[z]; s[1] = v.zoneRange[z]; s[2] = v.zoneFalloff[z]; s[3] = SM_T5_SMAX_ZONE;
    }
    sm_zone_policy(exp2(v.localContrast / 100.0) - 1.0, v.zonePivot, nominal, &p->curve);
    int slots = 0;
    for (int i = 0; i < SM_T5_SLOTS; ++i) slots |= p->curve.zoneE[i] != 0.0f;
    p->toneOn = (p->curve.conC != 0.0f || slots) ? 1 : 0;
    // Local Highlights: the main node's shoulder, landing the recorded top on the node's own Bianco at -100
    double amount = fabs(v.localHighlights) / 100.0;
    amount *= 1.5 - 0.5 * amount;
    if (v.localHighlights > 0.0) {
        p->hlE = (float)(amount * SM_T5_HL_CPLUS);
    } else if (v.localHighlights < 0.0) {
        const double top = SM_T5_HL_TOP, land = fmin(v.localWhite, top - SM_T5_HL_MINPULL);
        const double D = sm_shoulder_dd(top - SM_DT_HL_START);
        const double k = D > 0.0 ? fmin(fmax(top - land, 0.0) / D, 1.0 - SM_T5_HL_SMIN) : 0.0;
        p->hlE = (float)(-amount * k);
        p->hlAmount = (float)amount;
        p->hlWhiteLin = (float)(SM_T5_GREY * exp2(fmax(v.localWhite, top - k * D)));
    }
    p->hlTop = (float)SM_T5_HL_TOP;
    p->hlStart = (float)SM_DT_HL_START;
    // Soglia bordi sets what counts as detail: lower, fewer halos and less texture kept
    p->hlT1 = (float)(0.7 * v.edgeThreshold);
    p->hlT2 = (float)(0.6 * v.edgeThreshold);
    p->hlB1 = (float)(0.3 * v.edgeThreshold);
    p->hlB2 = (float)(0.2 * v.edgeThreshold);
    p->lam = (float)(v.preserveDetail / 100.0);
    p->tau0 = (float)v.noiseThreshold;
    p->clarity = (float)(v.clarity / 100.0);
    p->clarityCenter = (float)v.clarityCenter;
    p->texture = (float)(v.texture / 100.0);

    p->hazeOn = v.dehaze != 0.0 ? 1 : 0;
    p->hazeOmega = v.dehaze > 0.0 ? (float)(0.006 * v.dehaze) : 0.0f;
    p->hazeMix = v.dehaze < 0.0 ? (float)(0.5 * (v.dehaze / 100.0) * (v.dehaze / 100.0)) : 0.0f;
    p->hazeLevel = (float)v.hazeLevel;
    double veil[3];
    dt_veil(v.hazeWarmth, space, veil);
    for (int c = 0; c < 3; ++c) {
        const double a = SM_T5_GREY * exp2(v.hazeLevel) * veil[c];
        p->hazeA[c] = (float)a;
        p->hazeInvA[c] = (float)(1.0 / a);
    }
    p->view = v.viewGain ? 1 : (v.viewBase ? 2 : 0);
    p->on = (p->toneOn || p->hlE != 0.0f || p->clarity != 0.0f || p->texture != 0.0f || p->hazeOn || p->view) ? 1 : 0;

    const float* a = SM_XYZ_TO_RGB + SM_T5_REF * 9;
    const float* b = SM_RGB_TO_XYZ + space * 9;
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j)
            p->toRef[i * 3 + j] = (float)((double)a[i * 3] * b[j] + (double)a[i * 3 + 1] * b[3 + j]
                                          + (double)a[i * 3 + 2] * b[6 + j]);
}
#endif
