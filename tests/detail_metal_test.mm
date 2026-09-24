// SPDX-License-Identifier: GPL-3.0-or-later
// The Detail node's Metal kernels against its CPU pipeline on a synthetic frame, every control.
// Prints "MAXDIFF x" (code values; a difference negligible in light near black is not counted) and,
// with --time, the GPU time of a UHD frame.
#import <Metal/Metal.h>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

#include "gen/DevelopMath.h"
#include "metal/MetalKernels.h"
#include "src/detail/DetailPasses.h"

static void frame(std::vector<float>& img, int W, int H)
{
    img.assign((size_t)W * H * 4, 1.0f);
    for (int y = 0; y < H; ++y)
        for (int x = 0; x < W; ++x) {
            float ev = y < H / 2 ? -3.0f + 5.0f * x / W : -4.5f;
            if (x > W * 0.6f && x < W * 0.8f && y > H * 0.55f && y < H * 0.85f) ev = 4.0f;
            ev += 0.12f * sinf(x * 1.7f) * cosf(y * 1.3f) + 0.02f * sinf(x * 12.9898f + y * 78.233f);
            const float tint[3] = { x < W / 3 ? 1.0f : 0.7f, x < W / 3 ? 0.9f : 0.85f, x < W / 3 ? 0.75f : 1.0f };
            for (int c = 0; c < 3; ++c) img[((size_t)y * W + x) * 4 + c] = sm_encode(0.18f * exp2f(ev) * tint[c], 9);
        }
    img[(size_t)(5 * W + 7) * 4] = NAN;
}

int main(int argc, char** argv)
{
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device) { printf("NO_DEVICE\n"); return 2; }
    id<MTLCommandQueue> queue = [device newCommandQueue];
    const bool timing = argc > 1 && !strcmp(argv[1], "--time");
    const int W = timing ? 3840 : 320, H = timing ? 2160 : 180;
    std::vector<float> img;
    frame(img, W, H);
    id<MTLBuffer> in = [device newBufferWithBytes:img.data() length:img.size() * 4 options:MTLResourceStorageModeShared];
    id<MTLBuffer> out = [device newBufferWithLength:img.size() * 4 options:MTLResourceStorageModeShared];
    Parallel serial = [](int n, const std::function<void(int, int)>& fn) { fn(0, n); };
    double worst = 0.0;
    for (int k = 0; k < 11; ++k) {
        SMDetailControls c = sm_detail_defaults();
        switch (k) {
        case 0: c.localHighlights = -100; c.localShadows = 80; break;
        case 1: c.localContrast = -60; c.clarity = 80; break;
        case 2: c.texture = 90; c.noiseThreshold = 0.02; break;
        case 3: c.texture = -90; c.clarity = -50; c.clarityCenter = 1.5; break;
        case 4: c.dehaze = 70; c.hazeWarmth = 40; c.hazeLevel = 1; break;
        case 5: c.dehaze = -50; c.localShadows = 40; break;
        case 6: c.zoneExp[2] = -2; c.zoneExp[1] = 1.5; c.zonePivot = 1; c.preserveDetail = 60; break;
        case 7: c.localHighlights = -80; c.viewGain = 1; break;
        case 8: c.viewBase = 1; c.detailRadius = 8; c.edgeThreshold = 0.25; break;
        case 9: c.localHighlights = 60; c.localContrast = 30; break;
        case 10: c.localHighlights = -100; c.localWhite = 4.5; c.texture = 40; break;
        }
        DetailParams p;
        dt_prepare(&p, W, H, timing ? H : 1080.0, 1.0, 8, 9, &c, timing ? SM_DT_GRID_BASE : 45);
        if (timing) {
            RunDetailKernels((__bridge void*)queue, p, W, (const float*)(__bridge void*)in, (float*)(__bridge void*)out);
            id<MTLCommandBuffer> warm = [queue commandBuffer];
            [warm commit];
            [warm waitUntilCompleted];
            const auto t0 = std::chrono::steady_clock::now();
            for (int r = 0; r < 5; ++r)
                RunDetailKernels((__bridge void*)queue, p, W, (const float*)(__bridge void*)in, (float*)(__bridge void*)out);
            id<MTLCommandBuffer> sync = [queue commandBuffer];
            [sync commit];
            [sync waitUntilCompleted];
            const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count() / 5;
            printf("case %d UHD %.2f ms\n", k, ms);
            continue;
        }
        std::vector<float> cpu(img.size());
        DetailScratch scratch;
        detailRenderCPU(p, img.data(), (size_t)W * 4, cpu.data(), (size_t)W * 4, serial, scratch);
        if (!RunDetailKernels((__bridge void*)queue, p, W, (const float*)(__bridge void*)in, (float*)(__bridge void*)out)) {
            printf("KERNEL_FAILED\n");
            return 1;
        }
        id<MTLCommandBuffer> sync = [queue commandBuffer];
        [sync commit];
        [sync waitUntilCompleted];
        const float* gpu = (const float*)out.contents;
        for (size_t i = 0; i < img.size(); ++i) {
            if (i % 4 == 3) { if (gpu[i] != img[i]) { printf("ALPHA_MISMATCH\n"); return 1; } continue; }
            if (std::isnan(cpu[i]) && std::isnan(gpu[i])) continue;
            if (fabsf(sm_decode(cpu[i], 9) - sm_decode(gpu[i], 9)) <= 2e-6f) continue;
            const double d = fabs((double)cpu[i] - gpu[i]);
            if (d > worst) worst = d;
        }
    }
    if (!timing) printf("MAXDIFF %.8f\n", worst);
    return 0;
}
