// SPDX-License-Identifier: GPL-3.0-or-later
#include "DetailPasses.h"

#include <algorithm>
#include <cmath>

// Every filter sums its terms in a fixed order (tests/model/detail.py does the same), so one
// thread and many give the same bits, and the Metal kernels can match within float rounding.
namespace {

using Plane = std::vector<float>;

void ensure(Plane& v, size_t n)
{
    if (v.size() < n) v.resize(n);
}

// The 1D filters run on `lanes` adjacent lines at once (lane l at in[j * stride + l]): the vertical pass
// walks rows of a column block instead of single columns. Each lane sums in the same order as one line.
const int kLanes = 32;

// Separable filter over a W x H plane: horizontal pass into tmp, vertical pass into out.
template <typename FH, typename FV>
void separable(const Parallel& par, const float* in, int W, int H, int W2, int H2, float* tmp, float* out,
               FH horizontal, FV vertical)
{
    par(H, [&](int b, int e) {
        for (int y = b; y < e; ++y) horizontal(in + (size_t)y * W, 1, W, tmp + (size_t)y * W2, 1, 1);
    });
    par((W2 + kLanes - 1) / kLanes, [&](int b, int e) {
        for (int x = b * kLanes; x < e * kLanes && x < W2; x += kLanes)
            vertical(tmp + x, W2, H, out + x, W2, std::min(kLanes, W2 - x));
    });
}

// out[i] of a tent reduction by s (edge samples replicated).
struct Tent
{
    int s, nOut;
    void operator()(const float* in, int stride, int n, float* out, int ostride, int lanes) const
    {
        float acc[kLanes];
        for (int i = 0; i < nOut; ++i) {
            const float c = (i + 0.5f) * s - 0.5f;
            float wsum = 0.0f;
            std::fill(acc, acc + lanes, 0.0f);
            for (int x = (int)std::floor(c - s) + 1; x < (int)std::ceil(c + s); ++x) {
                const float w = s - std::fabs(x - c);
                if (w <= 0.0f) continue;
                const float* row = in + (size_t)(x < 0 ? 0 : (x > n - 1 ? n - 1 : x)) * stride;
                for (int l = 0; l < lanes; ++l) acc[l] += w * row[l];
                wsum += w;
            }
            float* o = out + (size_t)i * ostride;
            for (int l = 0; l < lanes; ++l) o[l] = acc[l] / wsum;
        }
    }
};

// Box of fractional radius r, window shrunk symmetrically at the borders.
struct Box
{
    float r;
    void operator()(const float* in, int stride, int n, float* out, int ostride, int lanes) const
    {
        float acc[kLanes];
        for (int i = 0; i < n; ++i) {
            const float rr = std::fmin(r, std::fmin((float)i, (float)(n - 1 - i)));
            const int k = (int)std::floor(rr);
            const float f = rr - k;
            std::fill(acc, acc + lanes, 0.0f);
            for (int j = i - k; j <= i + k; ++j) {
                const float* row = in + (size_t)j * stride;
                for (int l = 0; l < lanes; ++l) acc[l] += row[l];
            }
            if (f > 0.0f) {
                const float *lo = in + (size_t)(i - k - 1) * stride, *hi = in + (size_t)(i + k + 1) * stride;
                for (int l = 0; l < lanes; ++l) acc[l] += f * (lo[l] + hi[l]);
            }
            float* o = out + (size_t)i * ostride;
            for (int l = 0; l < lanes; ++l) o[l] = acc[l] / (2.0f * rr + 1.0f);
        }
    }
};

// Gaussian from its half kernel, renormalised over the taps inside the plane.
struct Gauss
{
    const float* half;
    int len;
    void operator()(const float* in, int stride, int n, float* out, int ostride, int lanes) const
    {
        const int R = len - 1;
        float acc[kLanes];
        for (int i = 0; i < n; ++i) {
            float wsum = 0.0f;
            std::fill(acc, acc + lanes, 0.0f);
            for (int k = -R; k <= R; ++k) {
                const int j = i + k;
                if (j < 0 || j >= n) continue;
                const float w = half[k < 0 ? -k : k];
                const float* row = in + (size_t)j * stride;
                for (int l = 0; l < lanes; ++l) acc[l] += w * row[l];
                wsum += w;
            }
            float* o = out + (size_t)i * ostride;
            for (int l = 0; l < lanes; ++l) o[l] = acc[l] / wsum;
        }
    }
};

void tent(const Parallel& par, const float* in, int W, int H, int s, float* out, Plane& tmp)
{
    const int w = (W + s - 1) / s, h = (H + s - 1) / s;
    ensure(tmp, (size_t)w * H);
    separable(par, in, W, H, w, h, tmp.data(), out, Tent{ s, w }, Tent{ s, h });
}

void box(const Parallel& par, const float* in, int w, int h, float rx, float ry, float* out, Plane& tmp)
{
    ensure(tmp, (size_t)w * h);
    separable(par, in, w, h, w, h, tmp.data(), out, Box{ rx }, Box{ ry });
}

void gauss(const Parallel& par, const float* in, int W, int H, const float* half, int len, float* out, Plane& tmp)
{
    ensure(tmp, (size_t)W * H);
    separable(par, in, W, H, W, H, tmp.data(), out, Gauss{ half, len }, Gauss{ half, len });
}

// Self-guided filter: averaged coefficients (a, b) of B = a L + b.
void guided(const Parallel& par, const float* I, int w, int h, float rx, float ry, float eps, float* a, float* b,
            Plane& mu, Plane& nu, Plane& tmp)
{
    const size_t n = (size_t)w * h;
    ensure(mu, n);
    ensure(nu, n);
    box(par, I, w, h, rx, ry, mu.data(), tmp);
    for (size_t i = 0; i < n; ++i) nu[i] = I[i] * I[i];
    box(par, nu.data(), w, h, rx, ry, nu.data(), tmp);
    for (size_t i = 0; i < n; ++i) {
        const float v = std::fmax(nu[i] - mu[i] * mu[i], 0.0f);
        const float ai = v / (v + eps);
        nu[i] = ai;
        mu[i] = mu[i] * (1.0f - ai);
    }
    box(par, nu.data(), w, h, rx, ry, a, tmp);
    box(par, mu.data(), w, h, rx, ry, b, tmp);
}

SMf3 decoded(const float* px, int gamma)
{
    return smf3(sm_decode(px[0], gamma), sm_decode(px[1], gamma), sm_decode(px[2], gamma));
}

bool finite3(SMf3 c) { return std::isfinite(c.x) && std::isfinite(c.y) && std::isfinite(c.z); }

}  // namespace

void detailRenderCPU(const DetailParams& p, const float* src, size_t srcRow, float* dst, size_t dstRow,
                     const Parallel& par, DetailScratch& s, DetailPlanes* planes)
{
    const int W = p.W, H = p.H, w = p.w, h = p.h;
    const size_t full = (size_t)W * H, grid = (size_t)w * h;
    const bool dehaze = p.hazeOn != 0;
    ensure(s.L0, full);
    if (dehaze) ensure(s.J, full * 3);   // Dehaze keeps the decoded source here, then dehazes it in place
    par(H, [&](int b, int e) {
        for (int y = b; y < e; ++y)
            for (int x = 0; x < W; ++x) {
                const size_t i = (size_t)y * W + x;
                SMf3 c = decoded(src + y * srcRow + (size_t)x * 4, p.gamma);
                s.L0[i] = finite3(c) ? dt_luma(c, p) : -16.0f;
                if (dehaze) { s.J[i * 3] = c.x; s.J[i * 3 + 1] = c.y; s.J[i * 3 + 2] = c.z; }
            }
    });
    const float* L = s.L0.data();

    if (dehaze) {
        ensure(s.L, full);
        if (p.hazeMix == 0.0f) {   // the transmission map, on the grid
            ensure(s.xa, full);
            for (int c = 0; c < 3; ++c) {
                ensure(s.ch[c], grid);
                par(H, [&](int b, int e) {
                    for (int y = b; y < e; ++y)
                        for (int x = 0; x < W; ++x) {
                            const size_t i = (size_t)y * W + x;
                            const SMf3 v = smf3(s.J[i * 3], s.J[i * 3 + 1], s.J[i * 3 + 2]);
                            const float cv = c == 0 ? v.x : (c == 1 ? v.y : v.z);
                            s.xa[i] = finite3(v) ? cv * p.hazeInvA[c] : 0.0f;
                        }
                });
                tent(par, s.xa.data(), W, H, p.s, s.ch[c].data(), s.tmp);
            }
            ensure(s.Lw, grid);
            tent(par, L, W, H, p.s, s.Lw.data(), s.tmp);
            ensure(s.E, grid);
            for (size_t i = 0; i < grid; ++i) s.E[i] = dt_dark_energy(smf3(s.ch[0][i], s.ch[1][i], s.ch[2][i]));
            box(par, s.E.data(), w, h, p.rpx, p.rpy, s.E.data(), s.tmp);
            // t_raw - 1 over the energy plane, the guide centred on the veil level: the float32 sums
            // below would otherwise cancel the small covariance away
            for (size_t i = 0; i < grid; ++i) {
                const float D = std::fmax(-0.05f * std::log(std::fmax(s.E[i], 1e-30f)), 0.0f);
                s.Lw[i] -= p.hazeLevel;
                s.E[i] = -p.hazeOmega * std::fmin(D, 1.0f) * (1.0f - sm_t5_ramp(s.Lw[i]));
            }
            Plane &mI = s.g0, &mp = s.g1, &mIp = s.g2, &mII = s.g3;   // joint guided filter
            ensure(mI, grid); ensure(mp, grid); ensure(mIp, grid); ensure(mII, grid);
            box(par, s.Lw.data(), w, h, p.rtx, p.rty, mI.data(), s.tmp);
            box(par, s.E.data(), w, h, p.rtx, p.rty, mp.data(), s.tmp);
            for (size_t i = 0; i < grid; ++i) { mIp[i] = s.Lw[i] * s.E[i]; mII[i] = s.Lw[i] * s.Lw[i]; }
            box(par, mIp.data(), w, h, p.rtx, p.rty, mIp.data(), s.tmp);
            box(par, mII.data(), w, h, p.rtx, p.rty, mII.data(), s.tmp);
            for (size_t i = 0; i < grid; ++i) {
                const float var = std::fmax(mII[i] - mI[i] * mI[i], 0.0f);
                const float a = (mIp[i] - mI[i] * mp[i]) / (var + p.epsT);
                mIp[i] = a;
                mII[i] = mp[i] - a * mI[i];
            }
            ensure(s.at, grid);
            ensure(s.bt, grid);
            box(par, mIp.data(), w, h, p.rtx, p.rty, s.at.data(), s.tmp);
            box(par, mII.data(), w, h, p.rtx, p.rty, s.bt.data(), s.tmp);
        }
        par(H, [&](int b, int e) {
            for (int y = b; y < e; ++y)
                for (int x = 0; x < W; ++x) {
                    const size_t i = (size_t)y * W + x;
                    const SMf3 v = smf3(s.J[i * 3], s.J[i * 3 + 1], s.J[i * 3 + 2]);
                    float t = 1.0f;
                    if (p.hazeMix == 0.0f)
                        t = sm_clamp(dt_bilinear(s.at.data(), w, h, p.s, x, y) * (L[i] - p.hazeLevel)
                                     + dt_bilinear(s.bt.data(), w, h, p.s, x, y) + 1.0f, SM_DT_HAZE_MIN_T, 1.0f);
                    SMf3 j = finite3(v) ? dt_haze_pixel(v, t, p) : v;
                    s.J[i * 3] = j.x; s.J[i * 3 + 1] = j.y; s.J[i * 3 + 2] = j.z;
                    s.L[i] = finite3(j) ? dt_luma(j, p) : -16.0f;
                }
        });
        L = s.L.data();
    }

    ensure(s.Lw, grid);
    tent(par, L, W, H, p.s, s.Lw.data(), s.tmp);
    ensure(s.aB, grid);
    ensure(s.bB, grid);
    guided(par, s.Lw.data(), w, h, p.rBx, p.rBy, p.eps, s.aB.data(), s.bB.data(), s.g0, s.g1, s.tmp);
    ensure(s.Dg, grid);
    if (p.clarity != 0.0f) {
        ensure(s.a2, grid); ensure(s.b2, grid); ensure(s.a3, grid); ensure(s.b3, grid);
        guided(par, s.Lw.data(), w, h, p.r2x, p.r2y, p.eps, s.a2.data(), s.b2.data(), s.g0, s.g1, s.tmp);
        guided(par, s.Lw.data(), w, h, p.r3x, p.r3y, p.eps, s.a3.data(), s.b3.data(), s.g0, s.g1, s.tmp);
        for (size_t i = 0; i < grid; ++i) s.Dg[i] = (s.a2[i] - s.a3[i]) * s.Lw[i] + (s.b2[i] - s.b3[i]);
    } else {
        std::fill(s.Dg.begin(), s.Dg.begin() + grid, 0.0f);
    }
    ensure(s.Gg, full);
    gauss(par, L, W, H, p.gG, p.nG, s.Gg.data(), s.tmp);
    if (p.texture != 0.0f) {
        ensure(s.G1, full);
        gauss(par, L, W, H, p.g1, p.n1, s.G1.data(), s.tmp);
        ensure(s.Lt, (size_t)p.wt * p.ht);
        ensure(s.G2, (size_t)p.wt * p.ht);
        tent(par, L, W, H, p.st, s.Lt.data(), s.tmp);
        gauss(par, s.Lt.data(), p.wt, p.ht, p.gT, p.nT, s.G2.data(), s.tmp);
    }
    if (planes) {
        planes->L.assign(L, L + full);
        planes->B.assign(full, 0.0f);
        planes->Dg.assign(full, 0.0f);
        planes->G.assign(full, 0.0f);
    }

    par(H, [&](int b, int e) {
        for (int y = b; y < e; ++y) {
            const float* in = src + y * srcRow;
            float* out = dst + y * dstRow;
            for (int x = 0; x < W; ++x, in += 4, out += 4) {
                const size_t i = (size_t)y * W + x;
                const float G1 = p.texture != 0.0f ? s.G1[i] : 0.0f;
                const float G2 = p.texture != 0.0f ? dt_bilinear(s.G2.data(), p.wt, p.ht, p.st, x, y) : 0.0f;
                const float Dg = dt_bilinear(s.Dg.data(), w, h, p.s, x, y);
                const DtOut o = dt_gain(L[i], dt_bilinear(s.Lw.data(), w, h, p.s, x, y), s.Gg[i],
                                        dt_bilinear(s.aB.data(), w, h, p.s, x, y),
                                        dt_bilinear(s.bB.data(), w, h, p.s, x, y), Dg, G1, G2, p);
                if (planes) {
                    planes->B[i] = o.B;
                    planes->Dg[i] = Dg;
                    planes->G[i] = o.G;
                }
                out[3] = in[3];
                const SMf3 v = decoded(in, p.gamma);
                if (!finite3(v)) {
                    out[0] = in[0]; out[1] = in[1]; out[2] = in[2];
                } else if (p.view == 1) {
                    const SMf3 c = dt_emit(dt_view_gain(o.G, L[i]), p);
                    out[0] = c.x; out[1] = c.y; out[2] = c.z;
                } else if (p.view == 2) {
                    const float g = sm_encode(SM_T5_GREY * SM_EXP2(o.B), p.gamma);
                    out[0] = out[1] = out[2] = g;
                } else if (o.G == 0.0f && !dehaze) {
                    out[0] = in[0]; out[1] = in[1]; out[2] = in[2];
                } else {
                    const SMf3 j = dt_apply(dehaze ? smf3(s.J[i * 3], s.J[i * 3 + 1], s.J[i * 3 + 2]) : v, o, p);
                    out[0] = sm_encode(j.x, p.gamma);
                    out[1] = sm_encode(j.y, p.gamma);
                    out[2] = sm_encode(j.z, p.gamma);
                }
            }
        }
    });
}
