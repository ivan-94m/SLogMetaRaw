// SPDX-License-Identifier: GPL-3.0-or-later
// The Toni and Zone controls of the develop node: one table used to define, read, enable and reset them.
#pragma once
#include <string>
#include <vector>

#include "ofxsImageEffect.h"

#include "../../gen/DevelopMath.h"

struct ToneSlider
{
    const char* name;
    const char* label;
    double SMToneControls::*field;
    const char* hint;
};
extern const ToneSlider kToneSliders[7];

void defineToneParams(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page, OFX::GroupParamDescriptor* tones,
                      OFX::GroupParamDescriptor* zones);
SMToneControls readToneControls(OFX::ImageEffect& effect, double time);
std::vector<std::string> toneParamNames();   // every control of Toni and Zone
void resetTones(OFX::ImageEffect& effect);   // "Azzera toni"
void resetZones(OFX::ImageEffect& effect);   // "Azzera zone"

// The 1.1 tone controls, kept by name (Resolve restores by name) only to say they were dropped.
void defineLegacyTones(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page);
std::string legacyTonesNote(OFX::ImageEffect& effect);   // "" when nothing was set
void fetchLegacyTones(OFX::ImageEffect& effect);          // at construction: no map insert while rendering
void clearLegacyTones(OFX::ImageEffect& effect);
