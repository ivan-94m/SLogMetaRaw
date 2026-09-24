// SPDX-License-Identifier: GPL-3.0-or-later
#include "ZoneParams.h"

#include "ParamDefs.h"

// Edges after the HDR palette (Resolve 21 manual: Shadow <= +1, Light >= -1, Specular >= +4); Black at -4.
const ZoneDef kZones[kZoneCount] = { { "Black", 0, -4.0, 1.0 }, { "Shadow", 0, 1.0, 2.0 },
                                     { "Light", 1, -1.0, 2.0 }, { "Specular", 1, 4.0, 1.0 } };

std::string zoneParamName(const std::string& prefix, int zone, const char* field)
{
    return prefix + kZones[zone].name + field;
}

void defineZoneParams(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page, OFX::GroupParamDescriptor* group,
                      const std::string& prefix, bool withSat)
{
    if (OFX::DoubleParamDescriptor* p = defineSlider(d, page, prefix + "Pivot", "Contrast Pivot", 0, -4, 4, -3, 3, 0.05,
            "Stop dal grigio 18% attorno a cui ruota Contrast", group))
        p->setDigits(2);
    for (int z = 0; z < kZoneCount; ++z) {
        const std::string label = kZones[z].name;
        const char* side = kZones[z].up ? "sopra" : "sotto";
        const std::string expHint = "Esposizione in stop dei toni " + std::string(side)
                                  + " di Range: dentro la zona e un guadagno puro, la texture resta intatta";
        if (auto* p = defineSlider(d, page, zoneParamName(prefix, z, "Exp"), label + " Exp", 0, -6, 6, -3, 3, 0.05,
                                   expHint.c_str(), group))
            p->setDigits(2);
        if (withSat) {
            if (auto* p = defineSlider(d, page, zoneParamName(prefix, z, "Sat"), label + " Sat", 0, -100, 100, -100, 100,
                                       0.1, "Saturazione della zona, a luminanza invariata", group))
                p->setDigits(2);
        }
        if (auto* p = defineSlider(d, page, zoneParamName(prefix, z, "Range"), label + " Range", kZones[z].range, -10, 10,
                                   -8, 8, 0.1, "Bordo della zona, in stop dal grigio 18%", group))
            p->setDigits(2);
        if (auto* p = defineSlider(d, page, zoneParamName(prefix, z, "Falloff"), label + " Falloff", kZones[z].falloff,
                                   0.5, 6, 0.5, 4, 0.05,
                                   "Larghezza della transizione in stop: oltre meta corsa si allarga da sola", group))
            p->setDigits(2);
    }
}

ZoneValues readZoneValues(OFX::ImageEffect& effect, const std::string& prefix, double time)
{
    ZoneValues v;
    auto get = [&](const std::string& name, double def) {
        return effect.paramExists(name) ? effect.fetchDoubleParam(name)->getValueAtTime(time) : def;
    };
    v.pivot = get(prefix + "Pivot", 0.0);
    for (int z = 0; z < kZoneCount; ++z) {
        v.exp[z] = get(zoneParamName(prefix, z, "Exp"), 0.0);
        v.sat[z] = get(zoneParamName(prefix, z, "Sat"), 0.0);
        v.range[z] = get(zoneParamName(prefix, z, "Range"), kZones[z].range);
        v.falloff[z] = get(zoneParamName(prefix, z, "Falloff"), kZones[z].falloff);
    }
    return v;
}

void resetZoneParams(OFX::ImageEffect& effect, const std::string& prefix)
{
    auto reset = [&](const std::string& name, double def) {
        if (!effect.paramExists(name)) return;
        OFX::DoubleParam* p = effect.fetchDoubleParam(name);
        p->deleteAllKeys();
        p->setValue(def);
    };
    reset(prefix + "Pivot", 0.0);
    for (int z = 0; z < kZoneCount; ++z) {
        reset(zoneParamName(prefix, z, "Exp"), 0.0);
        reset(zoneParamName(prefix, z, "Sat"), 0.0);
        reset(zoneParamName(prefix, z, "Range"), kZones[z].range);
        reset(zoneParamName(prefix, z, "Falloff"), kZones[z].falloff);
    }
}
