// SPDX-License-Identifier: GPL-3.0-or-later
// Runs the Develop kernel (compiled at runtime, as Resolve does) on random pixels and compares it
// with the CPU path. Prints MAXDIFF and FMA (a*b+c that is exactly 0 only without contraction).
#import <Metal/Metal.h>
#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "gen/DevelopMath.h"
#include "gen/MetalSource.inc"
#include "metal/MetalContext.h"
#include "metal/MetalKernels.h"

static float fmaProbe(id<MTLDevice> device, id<MTLCommandQueue> queue)
{
    id<MTLComputePipelineState> pipeline = metalPipeline(device, kMetalDevelop, "SLogMetaRawFmaProbe");
    if (!pipeline) return NAN;
    const float in[3] = { 1.0f + 0x1p-13f, 1.0f - 0x1p-13f, -1.0f };
    id<MTLBuffer> a = [device newBufferWithBytes:in length:sizeof(in) options:MTLResourceStorageModeShared];
    id<MTLBuffer> b = [device newBufferWithLength:sizeof(float) options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
    [enc setComputePipelineState:pipeline];
    [enc setBuffer:a offset:0 atIndex:0];
    [enc setBuffer:b offset:0 atIndex:1];
    [enc dispatchThreads:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
    [enc endEncoding];
    [cb commit];
    [cb waitUntilCompleted];
    return ((float*)b.contents)[0];
}

int main()
{
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device) { printf("NO_DEVICE\n"); return 2; }
    id<MTLCommandQueue> queue = [device newCommandQueue];
    const int W = 64, H = 16, N = W * H * 4;
    srand(7);
    double worst = 0.0;
    // ns, ng, os, og, levelFix, levelSpace, levelGamma, hostFull, fcMode
    int configs[][9] = { {0,0,0,0, 0,0,0,0, 0}, {0,0,1,3, 0,0,0,0, 0}, {8,9,8,9, 0,0,0,0, 0},
                         {6,8,0,0, 0,0,0,0, 0}, {10,10,1,5, 0,0,0,0, 0}, {0,0,2,6, 0,0,0,0, 0},
                         {8,9,8,9, 1,8,9,0, 0}, {0,0,0,0, 1,8,9,0, 0}, {0,0,1,3, 1,7,9,1, 0},
                         {10,10,10,10, 1,8,9,0, 0}, {6,8,6,8, 1,6,8,1, 0},
                         {8,9,8,9, 0,0,0,0, 1}, {0,0,1,3, 0,0,0,0, 1}, {8,9,8,9, 0,0,0,0, 2},
                         {0,0,0,0, 0,0,0,0, 2}, {10,10,1,5, 0,0,0,0, 3}, {8,9,8,9, 1,8,9,0, 2} };
    for (auto& c : configs) {
        DevelopParams p = {};
        p.nodeSpace = c[0]; p.nodeGamma = c[1]; p.outSpace = c[2]; p.outGamma = c[3];
        p.convert = (c[0] != c[2] || c[1] != c[3]);
        if (c[4]) sm_set_level_fix(&p, c[5], c[6], c[7]);
        p.fcMode = c[8];
        if (p.fcMode >= 2) sm_fc_calibrate(&p, 5600.0, 0.0);
        p.expo = 1.4f;
        sm_set_white_balance(&p, 4000.0, 0.0, 6200.0, 8.0);
        SMToneControls tone = sm_tone_defaults();
        const int variant = (int)(&c - configs) % 4;   // every tone path, extremes included
        tone.contrast = 15; tone.highlights = -30; tone.shadows = 20; tone.saturation = 10; tone.vibrance = 30;
        if (variant == 1) {
            tone.blacks = -100; tone.whites = 100; tone.zoneExp[1] = -6; tone.zoneSat[0] = -100; tone.highlights = -100;
        }
        if (variant == 2) { tone.blacks = 100; tone.softClip = 1; tone.softClipLevel = 1.5; tone.softClipColor = 60; }
        if (variant == 3) {
            tone.contrast = -100; tone.zoneExp[2] = 6; tone.zoneExp[3] = -6; tone.zoneFalloff[3] = 0.5; tone.highlights = 100;
        }
        sm_set_tone(&p, &tone, p.outSpace, p.convert, p.expo);
        id<MTLBuffer> in = [device newBufferWithLength:N * sizeof(float) options:MTLResourceStorageModeShared];
        id<MTLBuffer> out = [device newBufferWithLength:N * sizeof(float) options:MTLResourceStorageModeShared];
        float* ip = (float*)in.contents;
        for (int i = 0; i < N; ++i) {   // code values in range, plus black, footroom and super-whites
            const float r = rand() / (float)RAND_MAX;
            ip[i] = (i / 4) % 8 == 7 ? -0.05f + 1.3f * r : 0.1f + 0.7f * r;
        }
        if (!RunDevelopKernel((__bridge void*)queue, W, H, W, p, (const float*)(__bridge void*)in,
                              (float*)(__bridge void*)out)) {
            printf("KERNEL_FAILED\n");
            return 1;
        }
        id<MTLCommandBuffer> sync = [queue commandBuffer];
        [sync commit];
        [sync waitUntilCompleted];
        float* op = (float*)out.contents;
        for (int i = 0; i < W * H; ++i) {
            SMf3 cpu = sm_develop(smf3(ip[i * 4], ip[i * 4 + 1], ip[i * 4 + 2]), p);
            const float gpu[3] = { op[i * 4], op[i * 4 + 1], op[i * 4 + 2] }, ref[3] = { cpu.x, cpu.y, cpu.z };
            const int gamma = p.convert ? p.outGamma : p.nodeGamma;
            for (int k = 0; k < 3; ++k) {
                // a pure power curve has infinite slope at 0: float noise in linear light near 0 (black, or an
                // out-of-gamut channel crossing 0 on its way to white) moves the code value visibly while the
                // light differs by nothing, so a difference under 2e-5 in light is not counted
                if (fabs(sm_decode(ref[k], gamma) - sm_decode(gpu[k], gamma)) <= 2e-5f) continue;
                worst = fmax(worst, fabs(ref[k] - gpu[k]) / fmax(1.0, fabs(ref[k])));
            }
            if (op[i * 4 + 3] != ip[i * 4 + 3]) { printf("ALPHA_MISMATCH\n"); return 1; }
        }
    }
    printf("MAXDIFF %.8f FMA %.10g\n", worst, fmaProbe(device, queue));
    return 0;
}
