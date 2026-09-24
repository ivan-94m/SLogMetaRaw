// SPDX-License-Identifier: GPL-3.0-or-later
// Compiled at runtime after kMetalPrelude (metal_stdlib + DevelopMath.h).
kernel void SLogMetaRawDevelop(constant int& p_Width [[buffer(11)]], constant int& p_Height [[buffer(12)]],
                               constant DevelopParams& p_Params [[buffer(13)]],
                               constant int& p_RowPixels [[buffer(14)]],
                               const device float* p_Input [[buffer(0)]], device float* p_Output [[buffer(8)]],
                               uint2 id [[thread_position_in_grid]])
{
    if ((int)id.x >= p_Width || (int)id.y >= p_Height) return;
    const int i = ((int)id.y * p_RowPixels + (int)id.x) * 4;
    SMf3 o = sm_develop(smf3(p_Input[i], p_Input[i + 1], p_Input[i + 2]), p_Params);
    p_Output[i] = o.x;
    p_Output[i + 1] = o.y;
    p_Output[i + 2] = o.z;
    p_Output[i + 3] = p_Input[i + 3];
}

// Test only: out = a*b + c must round like the CPU build (no fused multiply-add).
kernel void SLogMetaRawFmaProbe(const device float* p_In [[buffer(0)]], device float* p_Out [[buffer(1)]],
                                uint id [[thread_position_in_grid]])
{
    p_Out[id] = p_In[id * 3] * p_In[id * 3 + 1] + p_In[id * 3 + 2];
}
