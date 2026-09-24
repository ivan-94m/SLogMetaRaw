// SPDX-License-Identifier: GPL-3.0-or-later
// The Detail node on the GPU: the passes of src/detail/DetailPasses.cpp, summing in the same order.
// Compiled at runtime after kMetalPrelude (metal_stdlib + DevelopMath.h).

struct DtPass {
    int inW, inH, outW, outH;   // plane sizes
    int s;                      // tent scale
    float r;                    // box radius along the pass
    int len;                    // gaussian half-kernel length
    int rowPixels;              // stride of the RGBA frames
};

kernel void dt_luma(const device float* src [[buffer(0)]], device float* L [[buffer(1)]],
                    constant DtPass& q [[buffer(2)]], constant DetailParams& p [[buffer(3)]],
                    uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= p.W || (int)id.y >= p.H) return;
    const int i = ((int)id.y * q.rowPixels + (int)id.x) * 4;
    SMf3 c = smf3(sm_decode(src[i], p.gamma), sm_decode(src[i + 1], p.gamma), sm_decode(src[i + 2], p.gamma));
    const bool finite = isfinite(c.x) && isfinite(c.y) && isfinite(c.z);
    L[(int)id.y * p.W + (int)id.x] = finite ? dt_luma(c, p) : -16.0f;
}

// Decoded channel c of the frame divided by the veil, 0 where the pixel is not finite.
kernel void dt_veil_ratio(const device float* src [[buffer(0)]], device float* out [[buffer(1)]],
                          constant DtPass& q [[buffer(2)]], constant DetailParams& p [[buffer(3)]],
                          constant int& channel [[buffer(4)]], uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= p.W || (int)id.y >= p.H) return;
    const int i = ((int)id.y * q.rowPixels + (int)id.x) * 4;
    SMf3 c = smf3(sm_decode(src[i], p.gamma), sm_decode(src[i + 1], p.gamma), sm_decode(src[i + 2], p.gamma));
    const bool finite = isfinite(c.x) && isfinite(c.y) && isfinite(c.z);
    const float v = channel == 0 ? c.x : (channel == 1 ? c.y : c.z);
    out[(int)id.y * p.W + (int)id.x] = finite ? v * p.hazeInvA[channel] : 0.0f;
}

inline float tent_at(const device float* in, int stride, int n, int i, int s)
{
    const float c = ((float)i + 0.5f) * (float)s - 0.5f;
    float acc = 0.0f, wsum = 0.0f;
    for (int x = (int)floor(c - (float)s) + 1; x < (int)ceil(c + (float)s); ++x) {
        const float w = (float)s - fabs((float)x - c);
        if (w <= 0.0f) continue;
        acc += w * in[(x < 0 ? 0 : (x > n - 1 ? n - 1 : x)) * stride];
        wsum += w;
    }
    return acc / wsum;
}

inline float box_at(const device float* in, int stride, int n, int i, float r)
{
    const float rr = fmin(r, fmin((float)i, (float)(n - 1 - i)));
    const int k = (int)floor(rr);
    const float f = rr - (float)k;
    float acc = 0.0f;
    for (int j = i - k; j <= i + k; ++j) acc += in[j * stride];
    if (f > 0.0f) acc += f * (in[(i - k - 1) * stride] + in[(i + k + 1) * stride]);
    return acc / (2.0f * rr + 1.0f);
}

inline float gauss_at(const device float* in, int stride, int n, int i, constant float* taps, int len)
{
    const int R = len - 1;
    float acc = 0.0f, wsum = 0.0f;
    for (int k = -R; k <= R; ++k) {
        const int j = i + k;
        if (j < 0 || j >= n) continue;
        const float w = taps[k < 0 ? -k : k];
        acc += w * in[j * stride];
        wsum += w;
    }
    return acc / wsum;
}

// Horizontal passes read row y of an inW-wide plane and write an outW-wide one; vertical passes read
// column x (outW wide) of an inH-tall plane and write outH rows.
kernel void dt_tent_h(const device float* in [[buffer(0)]], device float* out [[buffer(1)]],
                      constant DtPass& q [[buffer(2)]], uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= q.outW || (int)id.y >= q.inH) return;
    out[(int)id.y * q.outW + (int)id.x] = tent_at(in + (int)id.y * q.inW, 1, q.inW, (int)id.x, q.s);
}
kernel void dt_tent_v(const device float* in [[buffer(0)]], device float* out [[buffer(1)]],
                      constant DtPass& q [[buffer(2)]], uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= q.outW || (int)id.y >= q.outH) return;
    out[(int)id.y * q.outW + (int)id.x] = tent_at(in + (int)id.x, q.outW, q.inH, (int)id.y, q.s);
}
kernel void dt_box_h(const device float* in [[buffer(0)]], device float* out [[buffer(1)]],
                     constant DtPass& q [[buffer(2)]], uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= q.inW || (int)id.y >= q.inH) return;
    out[(int)id.y * q.inW + (int)id.x] = box_at(in + (int)id.y * q.inW, 1, q.inW, (int)id.x, q.r);
}
kernel void dt_box_v(const device float* in [[buffer(0)]], device float* out [[buffer(1)]],
                     constant DtPass& q [[buffer(2)]], uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= q.inW || (int)id.y >= q.inH) return;
    out[(int)id.y * q.inW + (int)id.x] = box_at(in + (int)id.x, q.inW, q.inH, (int)id.y, q.r);
}
kernel void dt_gauss_h(const device float* in [[buffer(0)]], device float* out [[buffer(1)]],
                       constant DtPass& q [[buffer(2)]], constant float* taps [[buffer(3)]],
                       uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= q.inW || (int)id.y >= q.inH) return;
    out[(int)id.y * q.inW + (int)id.x] = gauss_at(in + (int)id.y * q.inW, 1, q.inW, (int)id.x, taps, q.len);
}
kernel void dt_gauss_v(const device float* in [[buffer(0)]], device float* out [[buffer(1)]],
                       constant DtPass& q [[buffer(2)]], constant float* taps [[buffer(3)]],
                       uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= q.inW || (int)id.y >= q.inH) return;
    out[(int)id.y * q.inW + (int)id.x] = gauss_at(in + (int)id.x, q.inW, q.inH, (int)id.y, taps, q.len);
}

kernel void dt_square(const device float* in [[buffer(0)]], device float* out [[buffer(1)]],
                      constant int& n [[buffer(2)]], uint id [[thread_position_in_grid]])
{
    if ((int)id < n) out[id] = in[id] * in[id];
}

// (mu, nu) -> the guided filter's (b, a) in place: mu becomes b, nu becomes a.
kernel void dt_gf_ab(device float* mu [[buffer(0)]], device float* nu [[buffer(1)]],
                     constant int& n [[buffer(2)]], constant float& eps [[buffer(3)]],
                     uint id [[thread_position_in_grid]])
{
    if ((int)id >= n) return;
    const float v = fmax(nu[id] - mu[id] * mu[id], 0.0f);
    const float a = v / (v + eps);
    nu[id] = a;
    mu[id] = mu[id] * (1.0f - a);
}

kernel void dt_dark(const device float* c0 [[buffer(0)]], const device float* c1 [[buffer(1)]],
                    const device float* c2 [[buffer(2)]], device float* E [[buffer(3)]],
                    constant int& n [[buffer(4)]], uint id [[thread_position_in_grid]])
{
    if ((int)id < n) E[id] = dt_dark_energy(smf3(c0[id], c1[id], c2[id]));
}

// Energy -> t_raw - 1; the guide Lw is centred on the veil level in place.
kernel void dt_traw(device float* E [[buffer(0)]], device float* Lw [[buffer(1)]],
                    constant int& n [[buffer(2)]], constant DetailParams& p [[buffer(3)]],
                    uint id [[thread_position_in_grid]])
{
    if ((int)id >= n) return;
    const float D = fmax(-0.05f * log(fmax(E[id], 1e-30f)), 0.0f);
    Lw[id] -= p.hazeLevel;
    E[id] = -p.hazeOmega * fmin(D, 1.0f) * (1.0f - sm_t5_ramp(Lw[id]));
}

kernel void dt_joint_products(const device float* I [[buffer(0)]], const device float* t [[buffer(1)]],
                              device float* It [[buffer(2)]], device float* II [[buffer(3)]],
                              constant int& n [[buffer(4)]], uint id [[thread_position_in_grid]])
{
    if ((int)id >= n) return;
    It[id] = I[id] * t[id];
    II[id] = I[id] * I[id];
}

kernel void dt_joint_ab(const device float* mI [[buffer(0)]], const device float* mp [[buffer(1)]],
                        device float* mIp [[buffer(2)]], device float* mII [[buffer(3)]],
                        constant int& n [[buffer(4)]], constant float& eps [[buffer(5)]],
                        uint id [[thread_position_in_grid]])
{
    if ((int)id >= n) return;
    const float var = fmax(mII[id] - mI[id] * mI[id], 0.0f);
    const float a = (mIp[id] - mI[id] * mp[id]) / (var + eps);
    mIp[id] = a;
    mII[id] = mp[id] - a * mI[id];
}

kernel void dt_dg(const device float* a2 [[buffer(0)]], const device float* b2 [[buffer(1)]],
                  const device float* a3 [[buffer(2)]], const device float* b3 [[buffer(3)]],
                  const device float* Lw [[buffer(4)]], device float* Dg [[buffer(5)]],
                  constant int& n [[buffer(6)]], uint id [[thread_position_in_grid]])
{
    if ((int)id < n) Dg[id] = (a2[id] - a3[id]) * Lw[id] + (b2[id] - b3[id]);
}

kernel void dt_zero(device float* out [[buffer(0)]], constant int& n [[buffer(1)]], uint id [[thread_position_in_grid]])
{
    if ((int)id < n) out[id] = 0.0f;
}

// Dehaze at full size: J (3 planes, W*H apart) and its L.
kernel void dt_haze(const device float* src [[buffer(0)]], const device float* L0 [[buffer(1)]],
                    const device float* at [[buffer(2)]], const device float* bt [[buffer(3)]],
                    device float* J [[buffer(4)]], device float* L [[buffer(5)]],
                    constant DtPass& q [[buffer(6)]], constant DetailParams& p [[buffer(7)]],
                    uint2 id [[thread_position_in_grid]])
{
    const int x = (int)id.x, y = (int)id.y;
    if (x >= p.W || y >= p.H) return;
    const int i = (y * q.rowPixels + x) * 4, o = y * p.W + x, n = p.W * p.H;
    SMf3 v = smf3(sm_decode(src[i], p.gamma), sm_decode(src[i + 1], p.gamma), sm_decode(src[i + 2], p.gamma));
    float t = 1.0f;
    if (p.hazeMix == 0.0f)
        t = sm_clamp(dt_bilinear(at, p.w, p.h, p.s, x, y) * (L0[o] - p.hazeLevel)
                     + dt_bilinear(bt, p.w, p.h, p.s, x, y) + 1.0f, SM_DT_HAZE_MIN_T, 1.0f);
    const bool finite = isfinite(v.x) && isfinite(v.y) && isfinite(v.z);
    SMf3 j = finite ? dt_haze_pixel(v, t, p) : v;
    J[o] = j.x;
    J[n + o] = j.y;
    J[2 * n + o] = j.z;
    const bool jf = isfinite(j.x) && isfinite(j.y) && isfinite(j.z);
    L[o] = jf ? dt_luma(j, p) : -16.0f;
}

kernel void dt_final(const device float* src [[buffer(0)]], device float* dst [[buffer(1)]],
                     const device float* L [[buffer(2)]], const device float* Lw [[buffer(3)]],
                     const device float* Gg [[buffer(4)]], const device float* aB [[buffer(5)]],
                     const device float* bB [[buffer(6)]], const device float* Dg [[buffer(7)]],
                     const device float* G1 [[buffer(8)]], const device float* G2 [[buffer(9)]],
                     const device float* J [[buffer(10)]], constant DtPass& q [[buffer(11)]],
                     constant DetailParams& p [[buffer(12)]], uint2 id [[thread_position_in_grid]])
{
    const int x = (int)id.x, y = (int)id.y;
    if (x >= p.W || y >= p.H) return;
    const int i = (y * q.rowPixels + x) * 4, o = y * p.W + x, n = p.W * p.H;
    const float g1 = p.texture != 0.0f ? G1[o] : 0.0f;
    const float g2 = p.texture != 0.0f ? dt_bilinear(G2, p.wt, p.ht, p.st, x, y) : 0.0f;
    const DtOut r = dt_gain(L[o], dt_bilinear(Lw, p.w, p.h, p.s, x, y), Gg[o], dt_bilinear(aB, p.w, p.h, p.s, x, y),
                            dt_bilinear(bB, p.w, p.h, p.s, x, y), dt_bilinear(Dg, p.w, p.h, p.s, x, y), g1, g2, p);
    dst[i + 3] = src[i + 3];
    SMf3 v = smf3(sm_decode(src[i], p.gamma), sm_decode(src[i + 1], p.gamma), sm_decode(src[i + 2], p.gamma));
    SMf3 out;
    if (!(isfinite(v.x) && isfinite(v.y) && isfinite(v.z))) {
        out = smf3(src[i], src[i + 1], src[i + 2]);
    } else if (p.view == 1) {
        out = dt_emit(dt_view_gain(r.G, L[o]), p);
    } else if (p.view == 2) {
        const float g = sm_encode(SM_T5_GREY * SM_EXP2(r.B), p.gamma);
        out = smf3(g, g, g);
    } else if (r.G == 0.0f && p.hazeOn == 0) {
        out = smf3(src[i], src[i + 1], src[i + 2]);
    } else {
        SMf3 j = dt_apply(p.hazeOn != 0 ? smf3(J[o], J[n + o], J[2 * n + o]) : v, r, p);
        out = smf3(sm_encode(j.x, p.gamma), sm_encode(j.y, p.gamma), sm_encode(j.z, p.gamma));
    }
    dst[i] = out.x;
    dst[i + 1] = out.y;
    dst[i + 2] = out.z;
}
