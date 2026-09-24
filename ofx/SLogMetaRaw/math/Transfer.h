// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "Common.h"

// codes: 0 DaVinci Intermediate, 1 Linear, 2 Gamma 2.2, 3 Gamma 2.4, 4 Gamma 2.6,
//        5 Rec.709 (BT.709 OETF), 6 sRGB, 7 SLog, 8 SLog2, 9 SLog3, 10 ACEScct

SM_FN float sm_spow(float x, float p) { return x < 0.0f ? -SM_POW(-x, p) : SM_POW(x, p); }

SM_FN float sm_slog_enc(float r) {  // Sony S-Log core, r = reflection / 0.9 (Sony papers)
    float y = r >= 0.0f ? 0.432699f * SM_LOG10(r + 0.037584f) + 0.616596f + 0.03f
                        : r * 5.0f + 0.030001222851889303f;
    return (y * 876.0f + 64.0f) / 1023.0f;
}
SM_FN float sm_slog_dec(float x) {
    float y = (x * 1023.0f - 64.0f) / 876.0f;
    return y >= 0.030001222851889303f ? SM_POW(10.0f, (y - 0.616596f - 0.03f) / 0.432699f) - 0.037584f
                                      : (y - 0.030001222851889303f) / 5.0f;
}

SM_FN float sm_encode(float y, int g) {
    if (g == 0) return y <= 0.00262409f ? y * 10.44426855f : (SM_LOG2(y + 0.0075f) + 7.0f) * 0.07329248f;
    if (g == 2) return sm_spow(y, 1.0f / 2.2f);
    if (g == 3) return sm_spow(y, 1.0f / 2.4f);
    if (g == 4) return sm_spow(y, 1.0f / 2.6f);
    if (g == 5) return y < 0.018f ? 4.5f * y : 1.099f * SM_POW(y, 0.45f) - 0.099f;
    if (g == 6) return y <= 0.0031308f ? 12.92f * y : 1.055f * SM_POW(y, 1.0f / 2.4f) - 0.055f;
    if (g == 7) return sm_slog_enc(y / 0.9f);
    if (g == 8) return sm_slog_enc(y * 155.0f / 219.0f / 0.9f);
    if (g == 9) return y >= 0.01125f ? (420.0f + SM_LOG10((y + 0.01f) / 0.19f) * 261.5f) / 1023.0f
                                     : (y * (171.2102946929f - 95.0f) / 0.01125f + 95.0f) / 1023.0f;
    if (g == 10) return y <= 0.0078125f ? 10.5402377416545f * y + 0.0729055341958355f : (SM_LOG2(y) + 9.72f) / 17.52f;
    return y;
}
SM_FN float sm_decode(float x, int g) {
    if (g == 0) return x <= 0.02740668f ? x / 10.44426855f : SM_EXP2(x / 0.07329248f - 7.0f) - 0.0075f;
    if (g == 2) return sm_spow(x, 2.2f);
    if (g == 3) return sm_spow(x, 2.4f);
    if (g == 4) return sm_spow(x, 2.6f);
    if (g == 5) return x < 0.081f ? x / 4.5f : SM_POW((x + 0.099f) / 1.099f, 1.0f / 0.45f);
    if (g == 6) return x <= 0.04045f ? x / 12.92f : SM_POW((x + 0.055f) / 1.055f, 2.4f);
    if (g == 7) return sm_slog_dec(x) * 0.9f;
    if (g == 8) return sm_slog_dec(x) * 0.9f * 219.0f / 155.0f;
    if (g == 9) return x >= 171.2102946929f / 1023.0f ? SM_POW(10.0f, (x * 1023.0f - 420.0f) / 261.5f) * 0.19f - 0.01f
                                                      : (x * 1023.0f - 95.0f) * 0.01125f / (171.2102946929f - 95.0f);
    if (g == 10) return x <= 0.155251141552511f ? (x - 0.0729055341958355f) / 10.5402377416545f : SM_EXP2(x * 17.52f - 9.72f);
    return x;
}
