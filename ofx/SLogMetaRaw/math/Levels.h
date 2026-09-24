// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "Params.h"
#include "Transfer.h"
#include "Gamut.h"

// Resolve decides Full vs Video before the node and OpenFX cannot report which (docs/DATA_LEVELS.md).
// The fix is an affine remap of code values, so it runs in the camera encoding, reached by an
// exact round trip from whatever space the node is in.
SM_FN SMf3 sm_fix_levels(SMf3 lin, SM_CREF(DevelopParams) p) {
    if (p.levelFix == 0) return lin;
    SMf3 cam = (p.levelSpace == p.nodeSpace) ? lin
             : sm_from_xyz(sm_to_xyz(lin, p.nodeSpace), p.levelSpace);
    SMf3 cv = smf3(sm_encode(cam.x, p.levelGamma), sm_encode(cam.y, p.levelGamma),
                   sm_encode(cam.z, p.levelGamma));
    cv = smf3(cv.x * p.levelGain + p.levelOffset, cv.y * p.levelGain + p.levelOffset,
              cv.z * p.levelGain + p.levelOffset);
    cam = smf3(sm_decode(cv.x, p.levelGamma), sm_decode(cv.y, p.levelGamma),
               sm_decode(cv.z, p.levelGamma));
    return (p.levelSpace == p.nodeSpace) ? cam
         : sm_from_xyz(sm_to_xyz(cam, p.levelSpace), p.nodeSpace);
}
