// SPDX-License-Identifier: GPL-3.0-or-later
// Kernels run on the host's queue and are never waited for (ofxGPURender.h). The pixel pointers
// Resolve hands over are MTLBuffer handles. A false return means nothing was encoded.
#pragma once
#include "../gen/DevelopMath.h"

bool RunDetailKernels(void* p_CmdQ, const DetailParams& p_Params, int p_RowPixels, const float* p_Input,
                      float* p_Output);
bool RunDevelopKernel(void* p_CmdQ, int p_Width, int p_Height, int p_RowPixels, const DevelopParams& p_Params,
                      const float* p_Input, float* p_Output);
