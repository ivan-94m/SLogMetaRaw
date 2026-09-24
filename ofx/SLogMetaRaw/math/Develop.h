// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "Params.h"
#include "Transfer.h"
#include "Gamut.h"
#include "Levels.h"
#include "Tone.h"
#include "Color.h"
#include "FalseColor.h"

SM_FN SMf3 sm_develop(SMf3 in, SM_CREF(DevelopParams) p) {
    if (p.bypass != 0 && p.levelFix == 0) return in;
    SMf3 lin = smf3(sm_decode(in.x, p.nodeGamma), sm_decode(in.y, p.nodeGamma),
                    sm_decode(in.z, p.nodeGamma));
    lin = sm_fix_levels(lin, p);
    if (p.bypass != 0)   // data level only: the develop is off for this clip
        return smf3(sm_encode(lin.x, p.nodeGamma), sm_encode(lin.y, p.nodeGamma),
                    sm_encode(lin.z, p.nodeGamma));
    lin = smf3(lin.x * p.expo, lin.y * p.expo, lin.z * p.expo);
    SMf3 xyz = sm_to_xyz(lin, p.nodeSpace);

    // white balance: von Kries in Bradford LMS, as-shot white -> chosen white
    SMf3 lms = sm_mul(SM_BRADFORD, 0, xyz);
    lms = smf3(lms.x * p.ratioL, lms.y * p.ratioM, lms.z * p.ratioS);
    xyz = sm_mul(SM_BRADFORD, 9, lms);
    xyz = smf3(xyz.x * p.norm, xyz.y * p.norm, xyz.z * p.norm);

    if (p.fcMode != 0) return sm_fc_emit(sm_false_color(xyz, p), p);
    if (p.toneOn != 0 || p.colorOn != 0 || p.curve.roofOn != 0) xyz = sm_tone5(xyz, p);

    const int space = p.convert != 0 ? p.outSpace : p.nodeSpace;
    const int gamma = p.convert != 0 ? p.outGamma : p.nodeGamma;
    SMf3 o = sm_from_xyz(xyz, space);
    return smf3(sm_encode(o.x, gamma), sm_encode(o.y, gamma), sm_encode(o.z, gamma));
}
