// SPDX-License-Identifier: GPL-3.0-or-later
#include "MetalKernels.h"

#include "MetalContext.h"
#include "../gen/MetalSource.inc"

bool RunDevelopKernel(void* p_CmdQ, int p_Width, int p_Height, int p_RowPixels, const DevelopParams& p_Params,
                      const float* p_Input, float* p_Output)
{
    id<MTLCommandQueue> queue = (__bridge id<MTLCommandQueue>)p_CmdQ;
    id<MTLComputePipelineState> pipeline = metalPipeline(queue.device, kMetalDevelop, "SLogMetaRawDevelop");
    if (!pipeline) return false;
    id<MTLBuffer> src = (__bridge id<MTLBuffer>)(void*)p_Input;
    id<MTLBuffer> dst = (__bridge id<MTLBuffer>)(void*)p_Output;
    id<MTLCommandBuffer> commands = [queue commandBuffer];
    commands.label = @"SLogMetaRawDevelop";
    id<MTLComputeCommandEncoder> encoder = [commands computeCommandEncoder];
    [encoder setComputePipelineState:pipeline];
    const NSUInteger width = pipeline.threadExecutionWidth;
    [encoder setBuffer:src offset:0 atIndex:0];
    [encoder setBuffer:dst offset:0 atIndex:8];
    [encoder setBytes:&p_Width length:sizeof(int) atIndex:11];
    [encoder setBytes:&p_Height length:sizeof(int) atIndex:12];
    [encoder setBytes:&p_Params length:sizeof(DevelopParams) atIndex:13];
    [encoder setBytes:&p_RowPixels length:sizeof(int) atIndex:14];
    [encoder dispatchThreadgroups:MTLSizeMake((p_Width + width - 1) / width, p_Height, 1)
            threadsPerThreadgroup:MTLSizeMake(width, 1, 1)];
    [encoder endEncoding];
    [commands commit];
    return true;
}
