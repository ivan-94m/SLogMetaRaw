// SPDX-License-Identifier: GPL-3.0-or-later
#include "MetalKernels.h"

#include <algorithm>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "MetalContext.h"
#include "../gen/MetalSource.inc"

namespace {

struct DtPass { int inW, inH, outW, outH; int s; float r; int len; int rowPixels; };

// Scratch planes of one frame size. The GPU runs after render() returns, so a set goes back to the
// pool only in the command buffer's completion handler.
struct Scratch
{
    std::map<std::string, id<MTLBuffer>> planes;
};

class Pool
{
public:
    std::shared_ptr<Scratch> acquire(id<MTLDevice> device, const std::string& key)
    {
        std::lock_guard<std::mutex> lock(m_Mutex);
        auto& byKey = m_Free[device];
        for (auto it = byKey.begin(); it != byKey.end();)   // another frame size: its memory goes
            it = it->first == key ? std::next(it) : byKey.erase(it);
        auto& list = byKey[key];
        if (list.empty()) return std::make_shared<Scratch>();
        std::shared_ptr<Scratch> s = list.back();
        list.pop_back();
        return s;
    }
    void release(id<MTLDevice> device, const std::string& key, const std::shared_ptr<Scratch>& s)
    {
        std::lock_guard<std::mutex> lock(m_Mutex);
        auto& list = m_Free[device][key];
        if (list.size() < 3) list.push_back(s);
    }

private:
    std::mutex m_Mutex;
    std::map<id<MTLDevice>, std::map<std::string, std::vector<std::shared_ptr<Scratch>>>> m_Free;
};

Pool& pool()
{
    static Pool* p = new Pool();   // never destroyed: completion handlers may run after unload starts
    return *p;
}

id<MTLBuffer> plane(id<MTLDevice> device, Scratch& s, const char* name, size_t floats)
{
    __strong id<MTLBuffer>& b = s.planes[name];
    if (!b || b.length < floats * sizeof(float))
        b = [device newBufferWithLength:std::max<size_t>(floats, 1) * sizeof(float) options:MTLResourceStorageModePrivate];
    return b;
}

class Encoder
{
public:
    Encoder(id<MTLDevice> device, id<MTLComputeCommandEncoder> enc) : m_Device(device), m_Enc(enc) {}
    bool ok = true;

    id<MTLComputePipelineState> use(const char* name)
    {
        id<MTLComputePipelineState> ps = metalPipeline(m_Device, kMetalDetail, name);
        if (!ps) ok = false;
        else [m_Enc setComputePipelineState:ps];
        return ps;
    }
    void grid2(id<MTLComputePipelineState> ps, int w, int h)
    {
        if (!ps) return;
        // heavy kernels can allow fewer than 256 threads per group on older GPUs
        const NSUInteger tw = ps.threadExecutionWidth;
        const NSUInteger th = std::min<NSUInteger>(16, std::max<NSUInteger>(1, ps.maxTotalThreadsPerThreadgroup / tw));
        [m_Enc dispatchThreads:MTLSizeMake(w, h, 1) threadsPerThreadgroup:MTLSizeMake(tw, th, 1)];
    }
    void grid1(id<MTLComputePipelineState> ps, int n)
    {
        if (!ps) return;
        [m_Enc dispatchThreads:MTLSizeMake(n, 1, 1) threadsPerThreadgroup:MTLSizeMake(ps.threadExecutionWidth, 1, 1)];
    }
    void buf(id<MTLBuffer> b, int i) { [m_Enc setBuffer:b offset:0 atIndex:i]; }
    template <typename T> void bytes(const T& v, int i) { [m_Enc setBytes:&v length:sizeof(T) atIndex:i]; }

    // separable filters, horizontal into tmp then vertical into out
    void tent(id<MTLBuffer> in, int W, int H, int s, id<MTLBuffer> tmp, id<MTLBuffer> out)
    {
        const int w = (W + s - 1) / s, h = (H + s - 1) / s;
        DtPass q = { W, H, w, h, s, 0.0f, 0, 0 };
        id<MTLComputePipelineState> ps = use("dt_tent_h");
        buf(in, 0); buf(tmp, 1); bytes(q, 2); grid2(ps, w, H);
        ps = use("dt_tent_v");
        buf(tmp, 0); buf(out, 1); bytes(q, 2); grid2(ps, w, h);
    }
    void box(id<MTLBuffer> in, int w, int h, float rx, float ry, id<MTLBuffer> tmp, id<MTLBuffer> out)
    {
        DtPass q = { w, h, w, h, 1, rx, 0, 0 };
        id<MTLComputePipelineState> ps = use("dt_box_h");
        buf(in, 0); buf(tmp, 1); bytes(q, 2); grid2(ps, w, h);
        q.r = ry;
        ps = use("dt_box_v");
        buf(tmp, 0); buf(out, 1); bytes(q, 2); grid2(ps, w, h);
    }
    void gauss(id<MTLBuffer> in, int W, int H, const float* half, int len, id<MTLBuffer> tmp, id<MTLBuffer> out)
    {
        DtPass q = { W, H, W, H, 1, 0.0f, len, 0 };
        id<MTLComputePipelineState> ps = use("dt_gauss_h");
        buf(in, 0); buf(tmp, 1); bytes(q, 2); [m_Enc setBytes:half length:sizeof(float) * len atIndex:3];
        grid2(ps, W, H);
        ps = use("dt_gauss_v");
        buf(tmp, 0); buf(out, 1); bytes(q, 2); [m_Enc setBytes:half length:sizeof(float) * len atIndex:3];
        grid2(ps, W, H);
    }
    void guided(id<MTLBuffer> I, int w, int h, float rx, float ry, float eps, id<MTLBuffer> tmp, id<MTLBuffer> mu,
                id<MTLBuffer> nu, id<MTLBuffer> a, id<MTLBuffer> b)
    {
        const int n = w * h;
        box(I, w, h, rx, ry, tmp, mu);
        id<MTLComputePipelineState> ps = use("dt_square");
        buf(I, 0); buf(nu, 1); bytes(n, 2); grid1(ps, n);
        box(nu, w, h, rx, ry, tmp, nu);
        ps = use("dt_gf_ab");
        buf(mu, 0); buf(nu, 1); bytes(n, 2); bytes(eps, 3); grid1(ps, n);
        box(nu, w, h, rx, ry, tmp, a);
        box(mu, w, h, rx, ry, tmp, b);
    }

private:
    id<MTLDevice> m_Device;
    id<MTLComputeCommandEncoder> m_Enc;
};

}  // namespace

bool RunDetailKernels(void* p_CmdQ, const DetailParams& p, int p_RowPixels, const float* p_Input, float* p_Output)
{
    id<MTLCommandQueue> queue = (__bridge id<MTLCommandQueue>)p_CmdQ;
    id<MTLDevice> device = queue.device;
    id<MTLBuffer> src = (__bridge id<MTLBuffer>)(void*)p_Input;
    id<MTLBuffer> dst = (__bridge id<MTLBuffer>)(void*)p_Output;
    const int W = p.W, H = p.H, w = p.w, h = p.h;
    const size_t full = (size_t)W * H, grid = (size_t)w * h;
    const bool dehaze = p.hazeOn != 0, transmission = dehaze && p.hazeMix == 0.0f;
    const std::string key = std::to_string(W) + "x" + std::to_string(H) + (dehaze ? "h" : "") + std::to_string(p.s)
                          + "/" + std::to_string(p.st);
    std::shared_ptr<Scratch> s = pool().acquire(device, key);
    auto P = [&](const char* name, size_t n) { return plane(device, *s, name, n); };

    id<MTLCommandBuffer> commands = [queue commandBuffer];
    commands.label = @"SLogMetaRawDetail";
    id<MTLComputeCommandEncoder> enc = [commands computeCommandEncoder];
    Encoder e(device, enc);
    DtPass frame = { W, H, W, H, 1, 0.0f, 0, p_RowPixels };
    const int ngrid = (int)grid;

    id<MTLBuffer> L0 = P("L0", full), tmpFull = P("tmpFull", full), tmpGrid = P("tmpGrid", std::max(grid, (size_t)w * H));
    id<MTLComputePipelineState> ps = e.use("dt_luma");
    e.buf(src, 0); e.buf(L0, 1); e.bytes(frame, 2); e.bytes(p, 3); e.grid2(ps, W, H);
    id<MTLBuffer> L = L0, J = P("J", dehaze ? full * 3 : 1);
    id<MTLBuffer> Lw = P("Lw", grid), at = P("at", grid), bt = P("bt", grid);
    if (dehaze) {
        if (transmission) {
            id<MTLBuffer> xa = P("xa", full), ch[3] = { P("c0", grid), P("c1", grid), P("c2", grid) };
            for (int c = 0; c < 3; ++c) {
                ps = e.use("dt_veil_ratio");
                e.buf(src, 0); e.buf(xa, 1); e.bytes(frame, 2); e.bytes(p, 3); e.bytes(c, 4); e.grid2(ps, W, H);
                e.tent(xa, W, H, p.s, tmpGrid, ch[c]);
            }
            e.tent(L0, W, H, p.s, tmpGrid, Lw);
            id<MTLBuffer> E = P("E", grid);
            ps = e.use("dt_dark");
            e.buf(ch[0], 0); e.buf(ch[1], 1); e.buf(ch[2], 2); e.buf(E, 3); e.bytes(ngrid, 4); e.grid1(ps, ngrid);
            e.box(E, w, h, p.rpx, p.rpy, tmpGrid, E);
            ps = e.use("dt_traw");
            e.buf(E, 0); e.buf(Lw, 1); e.bytes(ngrid, 2); e.bytes(p, 3); e.grid1(ps, ngrid);
            id<MTLBuffer> mI = P("g0", grid), mp = P("g1", grid), mIp = P("g2", grid), mII = P("g3", grid);
            e.box(Lw, w, h, p.rtx, p.rty, tmpGrid, mI);
            e.box(E, w, h, p.rtx, p.rty, tmpGrid, mp);
            ps = e.use("dt_joint_products");
            e.buf(Lw, 0); e.buf(E, 1); e.buf(mIp, 2); e.buf(mII, 3); e.bytes(ngrid, 4); e.grid1(ps, ngrid);
            e.box(mIp, w, h, p.rtx, p.rty, tmpGrid, mIp);
            e.box(mII, w, h, p.rtx, p.rty, tmpGrid, mII);
            ps = e.use("dt_joint_ab");
            e.buf(mI, 0); e.buf(mp, 1); e.buf(mIp, 2); e.buf(mII, 3); e.bytes(ngrid, 4); e.bytes(p.epsT, 5);
            e.grid1(ps, ngrid);
            e.box(mIp, w, h, p.rtx, p.rty, tmpGrid, at);
            e.box(mII, w, h, p.rtx, p.rty, tmpGrid, bt);
        }
        L = P("L", full);
        ps = e.use("dt_haze");
        e.buf(src, 0); e.buf(L0, 1); e.buf(at, 2); e.buf(bt, 3); e.buf(J, 4); e.buf(L, 5); e.bytes(frame, 6);
        e.bytes(p, 7); e.grid2(ps, W, H);
    }

    e.tent(L, W, H, p.s, tmpGrid, Lw);
    id<MTLBuffer> aB = P("aB", grid), bB = P("bB", grid), mu = P("g0", grid), nu = P("g1", grid), Dg = P("Dg", grid);
    e.guided(Lw, w, h, p.rBx, p.rBy, p.eps, tmpGrid, mu, nu, aB, bB);
    if (p.clarity != 0.0f) {
        id<MTLBuffer> a2 = P("a2", grid), b2 = P("b2", grid), a3 = P("a3", grid), b3 = P("b3", grid);
        e.guided(Lw, w, h, p.r2x, p.r2y, p.eps, tmpGrid, mu, nu, a2, b2);
        e.guided(Lw, w, h, p.r3x, p.r3y, p.eps, tmpGrid, mu, nu, a3, b3);
        ps = e.use("dt_dg");
        e.buf(a2, 0); e.buf(b2, 1); e.buf(a3, 2); e.buf(b3, 3); e.buf(Lw, 4); e.buf(Dg, 5); e.bytes(ngrid, 6);
        e.grid1(ps, ngrid);
    } else {
        ps = e.use("dt_zero");
        e.buf(Dg, 0); e.bytes(ngrid, 1); e.grid1(ps, ngrid);
    }
    id<MTLBuffer> Gg = P("Gg", full), G1 = P("G1", p.texture != 0.0f ? full : 1);
    id<MTLBuffer> G2 = P("G2", p.texture != 0.0f ? (size_t)p.wt * p.ht : 1);
    e.gauss(L, W, H, p.gG, p.nG, tmpFull, Gg);
    if (p.texture != 0.0f) {
        e.gauss(L, W, H, p.g1, p.n1, tmpFull, G1);
        id<MTLBuffer> Lt = P("Lt", (size_t)p.wt * p.ht);
        e.tent(L, W, H, p.st, P("tmpTex", (size_t)p.wt * H), Lt);
        e.gauss(Lt, p.wt, p.ht, p.gT, p.nT, P("tmpTex", (size_t)p.wt * H), G2);
    }
    ps = e.use("dt_final");
    e.buf(src, 0); e.buf(dst, 1); e.buf(L, 2); e.buf(Lw, 3); e.buf(Gg, 4); e.buf(aB, 5); e.buf(bB, 6); e.buf(Dg, 7);
    e.buf(G1, 8); e.buf(G2, 9); e.buf(J, 10); e.bytes(frame, 11); e.bytes(p, 12);
    e.grid2(ps, W, H);
    [enc endEncoding];
    if (!e.ok) return false;
    [commands addCompletedHandler:^(id<MTLCommandBuffer>) { pool().release(device, key, s); }];
    [commands commit];
    return true;
}
