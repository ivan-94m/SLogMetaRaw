// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "Common.h"
#include "../gen/GamutMatrices.h"

// codes: 0 DaVinci WG, 1 Rec.709, 2 Rec.2020, 3 P3 D65, 4 P3 D60, 5 P3 DCI, 6 S-Gamut,
//        7 S-Gamut3, 8 S-Gamut3.Cine, 9 ACES AP0, 10 ACES AP1 (all adapted to D65)

SM_FN SMf3 sm_mul(SM_CPTR m, int o, SMf3 c) {
    return smf3(m[o] * c.x + m[o + 1] * c.y + m[o + 2] * c.z,
                m[o + 3] * c.x + m[o + 4] * c.y + m[o + 5] * c.z,
                m[o + 6] * c.x + m[o + 7] * c.y + m[o + 8] * c.z);
}
SM_FN SMf3 sm_to_xyz(SMf3 c, int s) { return sm_mul(SM_RGB_TO_XYZ, s * 9, c); }
SM_FN SMf3 sm_from_xyz(SMf3 c, int s) { return sm_mul(SM_XYZ_TO_RGB, s * 9, c); }

SM_CONST float SM_BRADFORD[18] = {
    0.8951f, 0.2664f, -0.1614f, -0.7502f, 1.7135f, 0.0367f, 0.0389f, -0.0685f, 1.0296f,
    0.98699291f, -0.14705426f, 0.15996265f, 0.43230527f, 0.51836027f, 0.04929123f,
    -0.00852866f, 0.04004282f, 0.96848669f };
