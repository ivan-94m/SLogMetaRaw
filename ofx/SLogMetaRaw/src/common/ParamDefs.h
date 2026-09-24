// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>

#include "ofxsImageEffect.h"

// DaVinci Resolve saves a node by parameter name: names are permanent, and a duplicate crashes the host.
void resetParamNames();          // at the start of every describeInContext call
bool claimName(const std::string& name);

OFX::StringParamDescriptor* defineInfo(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                       OFX::GroupParamDescriptor* group, const std::string& name,
                                       const std::string& label, const std::string& def = "—");
OFX::DoubleParamDescriptor* defineSlider(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                         const std::string& name, const std::string& label, double def,
                                         double lo, double hi, double dlo, double dhi, double inc,
                                         const char* hint = nullptr, OFX::GroupParamDescriptor* group = nullptr);
OFX::BooleanParamDescriptor* defineToggle(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                          const std::string& name, const std::string& label, const char* icon,
                                          const char* hint, OFX::GroupParamDescriptor* group = nullptr);
OFX::BooleanParamDescriptor* defineCheck(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                         const std::string& name, const std::string& label, bool def,
                                         const char* hint, OFX::GroupParamDescriptor* group = nullptr);
OFX::ChoiceParamDescriptor* defineChoice(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                         const std::string& name, const std::string& label,
                                         const char* const* options, int count, int def, const char* hint = nullptr,
                                         OFX::GroupParamDescriptor* group = nullptr);
OFX::PushButtonParamDescriptor* defineButton(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                             const std::string& name, const std::string& label, const char* hint,
                                             OFX::GroupParamDescriptor* group = nullptr);
OFX::GroupParamDescriptor* defineGroup(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                       const std::string& name, const std::string& label, bool open);

template <typename T>
void hideParam(T* p, OFX::PageParamDescriptor* page)
{
    if (!p) return;
    p->setIsSecret(true);
    p->setAnimates(false);
    page->addChild(*p);
}
OFX::DoubleParamDescriptor* defineHiddenDouble(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                               const std::string& name, double def);
OFX::IntParamDescriptor* defineHiddenInt(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page,
                                         const std::string& name, int def);

// Contexts, depth, tiles and colour management shared by both plugins.
enum SpatialMode { kPointwiseLutSafe, kSpatial };
void describeEffectCommon(OFX::ImageEffectDescriptor& d, const char* name, const char* description,
                          const char* icon, SpatialMode mode);
void defineClips(OFX::ImageEffectDescriptor& d);
