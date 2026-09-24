// SPDX-License-Identifier: GPL-3.0-or-later
#include "ColourSpaces.h"

const char* const kSpaceNames[kSpaceCount] = { "DaVinci WG", "Rec.709", "Rec.2020", "P3 D65", "P3 D60", "P3 DCI",
                                               "S-Gamut", "S-Gamut3", "S-Gamut3.Cine", "ACES AP0", "ACES AP1" };
const char* const kGammaNames[kGammaCount] = { "DaVinci Intermediate", "Linear", "Gamma 2.2", "Gamma 2.4",
                                               "Gamma 2.6", "Rec.709", "sRGB", "SLog", "SLog2", "SLog3", "ACEScct" };
const char* const kLevelNames[2] = { "Video (64-940)", "Full (0-1023)" };
const int kNodeInputPairs[kNodeInputCount][2] = { { 0, 0 }, { 0, 0 }, { 8, 9 }, { 7, 9 }, { 6, 8 }, { 10, 10 } };
const char* const kNodeInputNames[kNodeInputCount] = { "Automatico", "DaVinci WG/Intermediate", "S-Gamut3.Cine/S-Log3",
                                                       "S-Gamut3/S-Log3", "S-Gamut/S-Log2", "ACES AP1/ACEScct" };

bool mapColourspace(const std::string& cs, int& space, int& gamma)
{
    struct Entry { const char* name; int space; int gamma; };
    static const Entry table[] = {
        { "davinci_intermediate_widegamut", 0, 0 }, { "lin_davinci_widegamut", 0, 1 },
        { "slog3_sgamut3cine", 8, 9 }, { "slog3_sgamut3", 7, 9 },
        { "slog3_venice_sgamut3cine", 8, 9 }, { "slog3_venice_sgamut3", 7, 9 },
        { "lin_sgamut3cine", 8, 1 }, { "lin_sgamut3", 7, 1 },
        { "ACEScct", 10, 10 }, { "ACEScg", 10, 1 }, { "ACES2065-1", 9, 1 },
        { "lin_rec709_srgb", 1, 1 }, { "lin_rec2020", 2, 1 }, { "lin_p3d65", 3, 1 },
        { "g24_rec709_tx", 1, 3 }, { "g22_rec709_tx", 1, 2 }, { "srgb_tx", 1, 6 },
        { "rec1886_rec709_display", 1, 3 }, { "camera_rec709", 1, 5 },
    };
    for (const Entry& e : table) {
        if (cs == e.name) { space = e.space; gamma = e.gamma; return true; }
    }
    return false;
}
