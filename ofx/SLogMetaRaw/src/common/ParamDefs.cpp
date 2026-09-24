// SPDX-License-Identifier: GPL-3.0-or-later
#include "ParamDefs.h"

#include <cstdio>
#include <set>

#include "ofxImageEffectExt.h"
#include "ofxColour.h"

using namespace OFX;

#define kOfxNativeConfig "ofx-native-v1.5_aces-v1.3_ocio-v2.3"

// Claimed per describeInContext call: the host calls it once per context, and a set shared
// between the calls would leave the second context with no parameters.
static std::set<std::string>& usedNames()
{
    static thread_local std::set<std::string> names;
    return names;
}

void resetParamNames() { usedNames().clear(); }

bool claimName(const std::string& name)
{
    if (!usedNames().insert(name).second) {
        fprintf(stderr, "S-Log MetaRaw: parametro duplicato \"%s\", ignorato\n", name.c_str());
        return false;
    }
    return true;
}

StringParamDescriptor* defineInfo(ImageEffectDescriptor& d, PageParamDescriptor* page, GroupParamDescriptor* group,
                                  const std::string& name, const std::string& label, const std::string& def)
{
    if (!claimName(name)) return nullptr;
    StringParamDescriptor* p = d.defineStringParam(name);
    p->setLabels(label, label, label);
    p->setStringType(eStringTypeSingleLine);
    p->setDefault(def);            // never an empty box before the metadata is read
    p->setEnabled(false);          // read-only
    p->setAnimates(false);
    p->setEvaluateOnChange(false);
    if (group) p->setParent(*group);
    page->addChild(*p);
    return p;
}

DoubleParamDescriptor* defineSlider(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                    const std::string& label, double def, double lo, double hi, double dlo, double dhi,
                                    double inc, const char* hint, GroupParamDescriptor* group)
{
    if (!claimName(name)) return nullptr;
    DoubleParamDescriptor* p = d.defineDoubleParam(name);
    p->setLabels(label, label, label);
    p->setScriptName(name);
    p->setDefault(def);
    p->setRange(lo, hi);
    p->setDisplayRange(dlo, dhi);
    p->setIncrement(inc);
    p->setDoubleType(eDoubleTypePlain);
    if (hint) p->setHint(hint);
    if (group) p->setParent(*group);
    page->addChild(*p);
    return p;
}

// OpenFX cannot put two controls on one row, so a toggle sits right above the slider it serves.
BooleanParamDescriptor* defineToggle(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                     const std::string& label, const char* icon, const char* hint,
                                     GroupParamDescriptor* group)
{
    BooleanParamDescriptor* p = defineCheck(d, page, name, label, false, hint, group);
    if (p) p->setIcon(icon, true);   // PNG in Contents/Resources
    return p;
}

BooleanParamDescriptor* defineCheck(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                    const std::string& label, bool def, const char* hint, GroupParamDescriptor* group)
{
    if (!claimName(name)) return nullptr;
    BooleanParamDescriptor* p = d.defineBooleanParam(name);
    p->setLabels(label, label, label);
    p->setDefault(def);
    if (hint) p->setHint(hint);
    p->setAnimates(false);
    if (group) p->setParent(*group);
    page->addChild(*p);
    return p;
}

ChoiceParamDescriptor* defineChoice(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                    const std::string& label, const char* const* options, int count, int def,
                                    const char* hint, GroupParamDescriptor* group)
{
    if (!claimName(name)) return nullptr;
    ChoiceParamDescriptor* p = d.defineChoiceParam(name);
    p->setLabels(label, label, label);
    for (int i = 0; i < count; ++i) p->appendOption(options[i]);
    p->setDefault(def);
    if (hint) p->setHint(hint);
    p->setAnimates(false);
    if (group) p->setParent(*group);
    page->addChild(*p);
    return p;
}

PushButtonParamDescriptor* defineButton(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                        const std::string& label, const char* hint, GroupParamDescriptor* group)
{
    if (!claimName(name)) return nullptr;
    PushButtonParamDescriptor* p = d.definePushButtonParam(name);
    p->setLabels(label, label, label);
    if (hint) p->setHint(hint);
    if (group) p->setParent(*group);
    page->addChild(*p);
    return p;
}

GroupParamDescriptor* defineGroup(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                  const std::string& label, bool open)
{
    if (!claimName(name)) return nullptr;
    GroupParamDescriptor* g = d.defineGroupParam(name);
    g->setLabels(label, label, label);
    g->setOpen(open);
    page->addChild(*g);
    return g;
}

DoubleParamDescriptor* defineHiddenDouble(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name,
                                          double def)
{
    if (!claimName(name)) return nullptr;
    DoubleParamDescriptor* p = d.defineDoubleParam(name);
    p->setDefault(def);
    hideParam(p, page);
    return p;
}

IntParamDescriptor* defineHiddenInt(ImageEffectDescriptor& d, PageParamDescriptor* page, const std::string& name, int def)
{
    if (!claimName(name)) return nullptr;
    IntParamDescriptor* p = d.defineIntParam(name);
    p->setDefault(def);
    hideParam(p, page);
    return p;
}

void describeEffectCommon(ImageEffectDescriptor& d, const char* name, const char* description, const char* icon,
                          SpatialMode mode)
{
    d.setLabels(name, name, name);
    d.setPluginGrouping("S-Log MetaRaw");
    d.setPluginDescription(description);
    d.getPropertySet().propSetString(kOfxPropIcon, "", 0, false);     // index 0 = SVG (none), 1 = PNG
    d.getPropertySet().propSetString(kOfxPropIcon, icon, 1, false);
    d.addSupportedContext(eContextFilter);
    d.addSupportedContext(eContextGeneral);
    d.addSupportedBitDepth(eBitDepthFloat);
    d.setSingleInstance(false);
    d.setHostFrameThreading(false);
    d.setSupportsMultiResolution(false);
    d.setSupportsTiles(false);
    d.setTemporalClipAccess(false);
    d.setRenderTwiceAlways(false);
    d.setSupportsMultipleClipPARs(false);
#ifdef __APPLE__
    d.setSupportsMetalRender(true);
#endif
    // Pointwise = Resolve may bake the node into a LUT (Generate LUT); a spatial node must say no.
    d.setNoSpatialAwareness(mode == kPointwiseLutSafe);
    d.getPropertySet().propSetString(kOfxImageEffectPropColourManagementStyle, kOfxImageEffectColourManagementFull, false);
    d.getPropertySet().propSetString(kOfxImageEffectPropColourManagementAvailableConfigs, kOfxNativeConfig, false);
}

void defineClips(ImageEffectDescriptor& d)
{
    ClipDescriptor* src = d.defineClip(kOfxImageEffectSimpleSourceClipName);
    src->addSupportedComponent(ePixelComponentRGBA);
    src->setTemporalClipAccess(false);
    src->setSupportsTiles(false);
    src->setIsMask(false);
    ClipDescriptor* dst = d.defineClip(kOfxImageEffectOutputClipName);
    dst->addSupportedComponent(ePixelComponentRGBA);
    dst->setSupportsTiles(false);
}
