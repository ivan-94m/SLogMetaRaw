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

int main() {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device) { printf("NO_DEVICE\n"); return 2; }
    id<MTLCommandQueue> queue = [device newCommandQueue];
    const int W = 64, H = 16, N = W * H * 4;
    srand(7);
    double worst = 0.0;
    int configs[][4] = { {0,0,0,0}, {0,0,1,3}, {8,9,8,9}, {6,8,0,0}, {10,10,1,5}, {0,0,2,6} };
    for (auto& c : configs) {
        DevelopParams p = {};
        p.nodeSpace = c[0]; p.nodeGamma = c[1]; p.outSpace = c[2]; p.outGamma = c[3];
        p.convert = (c[0] != c[2] || c[1] != c[3]);
        p.expo = 1.4f;
        sm_set_white_balance(&p, 4000.0, 0.0, 6200.0, 8.0);
        p.shadows = 0.2f; p.highlights = -0.3f; p.contrast = 0.15f; p.saturation = 0.1f; p.boost = 0.3f;
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
