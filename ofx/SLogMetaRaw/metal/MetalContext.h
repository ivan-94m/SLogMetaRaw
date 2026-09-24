// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#import <Metal/Metal.h>

// Compute pipeline for a kernel of one of the generated sources, compiled once per device.
id<MTLComputePipelineState> metalPipeline(id<MTLDevice> device, const char* source, const char* function);
