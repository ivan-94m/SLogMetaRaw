// SPDX-License-Identifier: GPL-3.0-or-later
// Compiles the SLogMetaRaw Metal kernel at runtime (like Resolve does), runs it on
// random pixels and compares with the CPU path (sm_develop). Prints the max difference.
#import <Metal/Metal.h>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>
#include "../ofx/SLogMetaRaw/DevelopMath.h"

bool RunMetalKernel(void* p_CmdQ, int p_Width, int p_Height, const DevelopParams& p_Params, const float* p_Input, float* p_Output);

// same as the plugin's neutralUV: where a neutral pixel lands after the white balance
static void neutralUV(double shotK, double shotT, double k, double t, double& u, double& v)
{
    DevelopParams q = DevelopParams();
    sm_set_white_balance(&q, shotK, shotT, k, t);
    const double d65[3] = { 0.95046, 1.0, 1.08906 };
    double lms[3], xyz[3];
    sm_bradford(d65, lms, 0);
    lms[0] *= q.ratioL; lms[1] *= q.ratioM; lms[2] *= q.ratioS;
    sm_bradford(lms, xyz, 1);
    const double X = xyz[0] * q.norm, Y = xyz[1] * q.norm, Z = xyz[2] * q.norm;
    const double d = X + 15.0 * Y + 3.0 * Z;
    u = d > 1e-9 ? 4.0 * X / d : 0.0;
    v = d > 1e-9 ? 6.0 * Y / d : 0.0;
}

int main() {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device) { printf("NO_DEVICE\n"); return 2; }
    id<MTLCommandQueue> queue = [device newCommandQueue];
    const int W = 64, H = 16, N = W * H * 4;
    srand(7);
    double worst = 0.0;
    // ns, ng, os, og, levelFix, levelSpace, levelGamma, levelDirection (0 video->full, 1 full->video), fcMode
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
        p.levelFix = c[4]; p.levelSpace = c[5]; p.levelGamma = c[6];
        if (c[4]) {
            if (c[7] == 0) { p.levelGain = 876.0f / 1023.0f; p.levelOffset = 64.0f / 1023.0f; }
            else           { p.levelGain = 1023.0f / 876.0f; p.levelOffset = -64.0f / 876.0f; }
        }
        p.fcMode = c[8];
        if (p.fcMode >= 2) {   // the calibration buildParams computes, for 5600 K tint 0
            double u0, v0, uk, vk, ut, vt;
            neutralUV(5600.0, 0.0, 5600.0, 0.0, u0, v0);
            neutralUV(5600.0, 0.0, 5700.0, 0.0, uk, vk);
            neutralUV(5600.0, 0.0, 5600.0, 5.0, ut, vt);
            const double a = (uk - u0) / 100.0, cc = (vk - v0) / 100.0;
            const double b = (ut - u0) / 5.0, e = (vt - v0) / 5.0;
            const double det = a * e - b * cc;
            p.fcU = (float)u0; p.fcV = (float)v0;
            p.fcKu = (float)(e / det);   p.fcKv = (float)(-b / det);
            p.fcTu = (float)(-cc / det); p.fcTv = (float)(a / det);
        }
        p.expo = 1.4f;
        sm_set_white_balance(&p, 4000.0, 0.0, 6200.0, 8.0);
        p.shadows = 0.2f; p.highlights = -0.3f; p.contrast = 0.15f; p.saturation = 0.1f; p.boost = 0.3f;
        p.chromaRecover = 0.35f;
        id<MTLBuffer> in = [device newBufferWithLength:N * sizeof(float) options:MTLResourceStorageModeShared];
        id<MTLBuffer> out = [device newBufferWithLength:N * sizeof(float) options:MTLResourceStorageModeShared];
        float* ip = (float*)in.contents;
        for (int i = 0; i < N; ++i) ip[i] = 0.1f + 0.7f * (rand() / (float)RAND_MAX);
        // Resolve passes MTLBuffer handles as the pixel pointers
        RunMetalKernel((__bridge void*)queue, W, H, p, (const float*)(__bridge void*)in, (float*)(__bridge void*)out);
        id<MTLCommandBuffer> sync = [queue commandBuffer];
        [sync commit];
        [sync waitUntilCompleted];
        float* op = (float*)out.contents;
        for (int i = 0; i < W * H; ++i) {
            SMf3 cpu = sm_develop(smf3(ip[i*4], ip[i*4+1], ip[i*4+2]), p);
            worst = fmax(worst, fabs(cpu.x - op[i*4]));
            worst = fmax(worst, fabs(cpu.y - op[i*4+1]));
            worst = fmax(worst, fabs(cpu.z - op[i*4+2]));
            if (op[i*4+3] != ip[i*4+3]) { printf("ALPHA_MISMATCH\n"); return 1; }
        }
    }
    printf("MAXDIFF %.8f\n", worst);
    return 0;
}
