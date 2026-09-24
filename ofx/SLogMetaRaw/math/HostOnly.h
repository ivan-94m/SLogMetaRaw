// SPDX-License-Identifier: GPL-3.0-or-later
// CPU only: parameter preparation, never compiled into a kernel.
#pragma once
#include "Params.h"
#include "Gamut.h"
#ifndef __METAL_VERSION__

// Planckian locus in CIE 1960 uv (Krystek 1985): smooth, within 1.4e-4 of the Planck integral on
// 1500-15000 K, with an analytic tangent. The Kim et al. piecewise cubic it replaces had seams at
// 2222 K and 4000 K that made the sliders reverse.
static const double SM_WB_KMIN = 1500.0, SM_WB_KMAX = 15000.0, SM_WB_TINT_MAX = 150.0;
static inline void sm_locus_uv(double t, double* u, double* v, double* nu, double* nv) {
    t = t < SM_WB_KMIN ? SM_WB_KMIN : (t > SM_WB_KMAX ? SM_WB_KMAX : t);
    const double au = 0.860117757 + 1.54118254e-4 * t + 1.28641212e-7 * t * t;
    const double bu = 1.0 + 8.42420235e-4 * t + 7.08145163e-7 * t * t;
    const double av = 0.317398726 + 4.22806245e-5 * t + 4.20481691e-8 * t * t;
    const double bv = 1.0 - 2.89741816e-5 * t + 1.61456053e-7 * t * t;
    const double du = ((1.54118254e-4 + 2.0 * 1.28641212e-7 * t) * bu - au * (8.42420235e-4 + 2.0 * 7.08145163e-7 * t)) / (bu * bu);
    const double dv = ((4.22806245e-5 + 2.0 * 4.20481691e-8 * t) * bv - av * (-2.89741816e-5 + 2.0 * 1.61456053e-7 * t)) / (bv * bv);
    const double len = sqrt(du * du + dv * dv);
    *u = au / bu;
    *v = av / bv;
    *nu = -dv / len;   // unit normal towards +v: a greener illuminant
    *nv = du / len;
    if (*nv < 0.0) { *nu = -*nu; *nv = -*nv; }
}
static inline void sm_uv_xyz(double u, double v, double out[3]) {
    const double d = 2.0 * u - 8.0 * v + 4.0, x = 3.0 * u / d, y = 2.0 * v / d;
    out[0] = x / y; out[1] = 1.0; out[2] = (1.0 - x - y) / y;
}
static inline double sm_bradford_s(double u, double v) {
    double w[3];
    sm_uv_xyz(u, v, w);
    return (double)SM_BRADFORD[6] * w[0] + (double)SM_BRADFORD[7] * w[1] + (double)SM_BRADFORD[8] * w[2];
}
// A green tint at low Kelvin drives the white's Bradford S cone through zero, and the adaptation then
// inverts. The green side is soft-limited so S keeps at least 30% of its value on the locus.
static inline double sm_green_limit(double u, double v, double nu, double nv) {
    const double target = 0.3 * sm_bradford_s(u, v);
    double lo = 0.0, hi = 0.2;
    for (int i = 0; i < 60; ++i) {
        const double m = 0.5 * (lo + hi);
        if (sm_bradford_s(u + nu * m, v + nv * m) > target) lo = m; else hi = m;
    }
    return lo;
}
// White of an illuminant at temperature k with tint (Duv * 3000, positive = greener illuminant, so
// raising Tint makes the image more magenta), as XYZ with Y = 1.
static inline void sm_white_xyz(double k, double tint, double out[3]) {
    double u, v, nu, nv;
    sm_locus_uv(k, &u, &v, &nu, &nv);
    tint = tint < -SM_WB_TINT_MAX ? -SM_WB_TINT_MAX : (tint > SM_WB_TINT_MAX ? SM_WB_TINT_MAX : tint);
    double d = tint / 3000.0;
    if (d > 0.0) {
        const double lim = sm_green_limit(u, v, nu, nv), a = 0.5 * lim, b = lim - a;
        if (d > a) d = a + b * (1.0 - exp(-(d - a) / b));
    }
    sm_uv_xyz(u + nu * d, v + nv * d, out);
}
static inline void sm_bradford(const double in[3], double out[3], int inverse) {
    const float* m = SM_BRADFORD + (inverse ? 9 : 0);
    for (int i = 0; i < 3; ++i)
        out[i] = m[i * 3] * in[0] + m[i * 3 + 1] * in[1] + m[i * 3 + 2] * in[2];
}
// White-balance fields of DevelopParams from as-shot and chosen Kelvin/tint.
static inline void sm_set_white_balance(DevelopParams* p, double shotK, double shotTint, double k, double tint) {
    double ws[3], wt[3], ls[3], lt[3];
    sm_white_xyz(shotK, shotTint, ws);
    sm_white_xyz(k, tint, wt);
    sm_bradford(ws, ls, 0);
    sm_bradford(wt, lt, 0);
    double r[3] = { ls[0] / lt[0], ls[1] / lt[1], ls[2] / lt[2] };
    const double d65[3] = { 0.95046, 1.0, 1.08906 };
    double l65[3], lr[3], nw[3];
    sm_bradford(d65, l65, 0);
    for (int i = 0; i < 3; ++i) lr[i] = l65[i] * r[i];
    sm_bradford(lr, nw, 1);
    p->ratioL = (float)r[0];
    p->ratioM = (float)r[1];
    p->ratioS = (float)r[2];
    p->norm = nw[1] > 0.0 ? (float)(1.0 / nw[1]) : 1.0f;
}

// CIE 1960 uv where a neutral (D65, the matrices' white) lands after the white balance.
static inline void sm_neutral_uv(double shotK, double shotT, double k, double t, double* u, double* v) {
    DevelopParams q = DevelopParams();
    sm_set_white_balance(&q, shotK, shotT, k, t);
    const double d65[3] = { 0.95046, 1.0, 1.08906 };
    double lms[3], xyz[3];
    sm_bradford(d65, lms, 0);
    lms[0] *= q.ratioL;
    lms[1] *= q.ratioM;
    lms[2] *= q.ratioS;
    sm_bradford(lms, xyz, 1);
    const double X = xyz[0] * q.norm, Y = xyz[1] * q.norm, Z = xyz[2] * q.norm;
    const double d = X + 15.0 * Y + 3.0 * Z;
    *u = d > 1e-9 ? 4.0 * X / d : 0.0;
    *v = d > 1e-9 ? 6.0 * Y / d : 0.0;
}

// Inverse of the WB sliders' response at k/t, so the temperature and tint views read in
// slider units. Returns 0 on a degenerate basis (the caller then shows the picture).
static inline int sm_fc_calibrate(DevelopParams* p, double k, double t) {
    double u0, v0, uk, vk, ut, vt;
    const double dk = k + 100.0 <= SM_WB_KMAX ? 100.0 : -100.0;   // the locus stops at KMAX
    const double dt = t + 5.0 <= SM_WB_TINT_MAX ? 5.0 : -5.0;
    sm_neutral_uv(k, t, k, t, &u0, &v0);
    sm_neutral_uv(k, t, k + dk, t, &uk, &vk);
    sm_neutral_uv(k, t, k, t + dt, &ut, &vt);
    const double a = (uk - u0) / dk, c = (vk - v0) / dk;
    const double b = (ut - u0) / dt, e = (vt - v0) / dt;
    const double det = a * e - b * c;
    p->fcU = (float)u0;
    p->fcV = (float)v0;
    if (fabs(det) <= 1e-12) return 0;
    p->fcKu = (float)(e / det);
    p->fcKv = (float)(-b / det);
    p->fcTu = (float)(-c / det);
    p->fcTv = (float)(a / det);
    return 1;
}

// Code-value remap for a clip decoded on the wrong scale (hostFull: 1 = Resolve decoded Full).
static inline void sm_set_level_fix(DevelopParams* p, int space, int gamma, int hostFull) {
    p->levelFix = 1;
    p->levelSpace = space;
    p->levelGamma = gamma;
    p->levelGain = hostFull ? 1023.0f / 876.0f : 876.0f / 1023.0f;
    p->levelOffset = hostFull ? -64.0f / 876.0f : 64.0f / 1023.0f;
}
#endif
