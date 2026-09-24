// SPDX-License-Identifier: GPL-3.0-or-later
#include "MetalContext.h"

#include <cstdio>
#include <map>
#include <mutex>
#include <string>
#include <utility>

#include "../gen/MetalSource.inc"

id<MTLComputePipelineState> metalPipeline(id<MTLDevice> device, const char* source, const char* function)
{
    static std::mutex mutex;
    static std::map<std::pair<id<MTLDevice>, std::string>, id<MTLComputePipelineState>> cache;
    static std::map<std::pair<id<MTLDevice>, std::string>, int> failures;
    std::lock_guard<std::mutex> lock(mutex);
    const auto key = std::make_pair(device, std::string(function));
    auto it = cache.find(key);
    if (it != cache.end()) return it->second;
    if (failures[key] >= 1) return nil;   // compiled once and failed: the source will not change

    MTLCompileOptions* options = [MTLCompileOptions new];
    options.languageVersion = MTLLanguageVersion2_4;   // the oldest macOS we ship for (12)
    if (@available(macOS 15.0, *)) {
        options.mathMode = MTLMathModeSafe;
        options.mathFloatingPointFunctions = MTLMathFloatingPointFunctionsPrecise;
    } else {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
        options.fastMathEnabled = NO;
#pragma clang diagnostic pop
    }
    NSError* err = nil;
    const std::string text = std::string(kMetalPrelude) + source;
    id<MTLLibrary> library = [device newLibraryWithSource:@(text.c_str()) options:options error:&err];
    id<MTLComputePipelineState> pipeline = nil;
    if (library) {
        id<MTLFunction> fn = [library newFunctionWithName:@(function)];
        if (fn) pipeline = [device newComputePipelineStateWithFunction:fn error:&err];
    }
    if (!pipeline) {
        fprintf(stderr, "S-Log MetaRaw: kernel Metal %s non compilato: %.2000s\n", function,
                err ? err.localizedDescription.UTF8String : "funzione mancante");
        ++failures[key];
        return nil;
    }
    cache[key] = pipeline;
    return pipeline;
}
