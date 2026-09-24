// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "Common.h"

#define SM_T5_SLOTS 7
#define SM_T5_UP 4         // slots below this act on the tones above their edge, the rest below

// The tone curve in stops, shared by both nodes: Contrast, the Highlights shoulder, the slots in their
// fixed order, Soft Clip. A slot with E = 0 is off, and so is the shoulder with hlE = 0.
struct SMToneCurve {
    float conC;                   // Contrast c, slope 1 + c at the pivot
    float conPivot;
    float hlE;                    // shoulder: T - t = hlE * D(t - hlStart), D' rising from 0 to 1
    float hlStart;                // grey taken through Contrast
    float zoneE[SM_T5_SLOTS];     // exposure of the slot in stops
    float zoneEdge[SM_T5_SLOTS];  // edge taken through Contrast and the shoulder: it stays put in scene stops
    float zoneK[SM_T5_SLOTS];     // slope limiter of the rho/psi law
    float zoneFill[SM_T5_SLOTS];  // width of the C2 entry
    int roofOn;                   // Soft Clip
    float roofStops;
    float roofRenorm;
};

// Only 4-byte scalars and arrays of them: the layout must be identical in C++ and Metal.
struct DevelopParams {
    int bypass;        // 1 = pass the image through untouched
    int convert;       // 1 = Color Space / Gamma differ from the node space
    int nodeSpace;     // gamut code of the image entering the node
    int nodeGamma;     // transfer code of the image entering the node
    int outSpace;
    int outGamma;
    float expo;        // chosen EI / EI at capture
    float ratioL;      // Bradford LMS white ratios (as-shot white / chosen white)
    float ratioM;
    float ratioS;
    float norm;        // keeps the luminance of D65 unchanged by the WB move
    int levelFix;      // 1 = rescale the code values before the log decode
    int levelSpace;    // gamut of the camera domain the rescale happens in
    int levelGamma;    // transfer of that domain
    float levelGain;   // code value -> code value, affine
    float levelOffset;
    int fcMode;        // false colour: 0 off, 1 exposure, 2 temperature, 3 tint, 4 zones
    float fcU;         // CIE 1960 uv of the working space white (D65)
    float fcV;
    float fcKu;        // uv deviation -> slider units, from sm_fc_calibrate
    float fcKv;
    float fcTu;
    float fcTv;
    // tone and colour, filled by sm_set_tone (math/ToneHost.h)
    int toneOn;
    float blkA;        // Blacks veil amplitude: > 0 takes veil away, < 0 adds it
    float blkRenorm;   // log2 gain that puts grey back after the veil
    SMToneCurve curve;
    float roofPurity;
    float roofLin;     // the Soft Clip roof, linear
    float hlAmount;    // Highlights < 0: its eased amount, the weight of the display-white taper
    float hlWhiteLin;  // Bianco, linear: the taper keeps every channel under it
    int hlTaperSpace;  // gamut the taper reads: the output one when converting to a display gamut, else Rec.709
    int colorOn;
    int refSpace;      // gamut R of the colour stage: the output one when converting, else Rec.2020
    float sat;
    float vib;
    float zSat[4];     // zone Sat, and the nominal edges / 1/falloffs its weights use (Black, Shadow, Light, Specular)
    float zNomEdge[4];
    float zNomInvF[4];
};
