// SPDX-License-Identifier: GPL-3.0-or-later
#include "ToneParams.h"

#include <cmath>
#include <cstdio>
#include <cstring>

#include "../common/ParamDefs.h"
#include "../common/ZoneParams.h"

// Camera Raw order and names; the maths behind them is exposure per zone in stops (math/Tone.h).
const ToneSlider kToneSliders[7] = {
    { "toneContrast", "Contrast", &SMToneControls::contrast,
      "Contrasto attorno al grigio 18% (Pivot in Zone): pendenza x2 a +100, x1/2 a -100. I bordi delle zone restano "
      "in stop di scena" },
    { "toneHighlights", "Highlights", &SMToneControls::highlights,
      "Negativo: spalla filmica, comprime le alte luci fino a portare il massimo registrato sul Bianco a -100 "
      "(almeno 1,5 stop piu giu); le luci piu compresse vanno verso il bianco senza cambiare tinta. "
      "Positivo: piu stacco nelle alte luci. Grigio e toni sotto restano fermi" },
    { "toneShadows", "Shadows", &SMToneControls::shadows,
      "Esposizione dei toni sotto -1 stop, 100 = 2 stop. Alza anche il nero: per tenerlo giu usa Blacks" },
    { "toneWhites", "Whites", &SMToneControls::whites,
      "Esposizione dei toni da +3,5 stop al clip, 100 = 1 stop" },
    { "toneBlacks", "Blacks", &SMToneControls::blacks,
      "Velo in luce lineare 5 stop sotto il grigio: -100 = nero giu di 3 stop, +100 = su di 1. Grigio fermo" },
    { "toneVibrance", "Vibrance", &SMToneControls::vibrance,
      "Saturazione pesata sui colori meno saturi, con gli incarnati protetti" },
    { "toneSaturation", "Saturation", &SMToneControls::saturation,
      "Saturazione a luminanza invariata, uguale in ogni spazio colore del nodo" } };

static const char* const kSoftClip[] = { "softClip", "softClipLevel", "softClipColor" };

void defineToneParams(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page, OFX::GroupParamDescriptor* tones,
                      OFX::GroupParamDescriptor* zones)
{
    for (const ToneSlider& t : kToneSliders) {
        if (auto* p = defineSlider(d, page, t.name, t.label, 0, -100, 100, -100, 100, 0.1, t.hint, tones))
            p->setDigits(2);
        // Bianco, next to the sliders that land on it, keeps the name softClipLevel (Soft Clip's roof too),
        // so grades saved with it still load it
        if (!strcmp(t.name, "toneWhites"))
            if (auto* p = defineSlider(d, page, "softClipLevel", "Bianco (stop)", 2.5, 1, 10, 1, 8, 0.05,
                                       "Dove arriva il massimo registrato con Highlights -100 e dove Soft Clip mette il "
                                       "tetto, in stop sopra il grigio 18%. 2,5 = bianco Rec.709 con un CST senza tone "
                                       "mapping; con un DRT (ACES, AgX, DaVinci) alza a 4-5", tones))
                p->setDigits(2);
    }
    defineButton(d, page, "toneReset", "Azzera toni", "Riporta a zero Contrast, Highlights, Shadows, Whites, Blacks, "
                 "Vibrance e Saturation. Esposizione, bilanciamento e Bianco non cambiano", tones);

    defineToggle(d, page, "fcZones", "False color: zone", "fc_zones.png",
                 "Colora ogni pixel con la zona che lo muove, misurata sulla stessa grandezza delle zone. "
                 "Dove due zone si sovrappongono le tinte si mescolano", zones);
    defineZoneParams(d, page, zones, "zone", true);
    defineCheck(d, page, "softClip", "Soft Clip", false,
                "Ripiega le alte luci verso il Bianco (in Toni), un tetto che non raggiungono mai: contenimento, "
                "non recupero", zones);
    if (auto* p = defineSlider(d, page, "softClipColor", "Soft Clip Color", 0, -100, 100, -100, 100, 0.1,
                               "Colore delle luci ripiegate sotto il Bianco: verso destra lo tiene, verso sinistra va "
                               "verso la pellicola, che schiarendo desatura", zones))
        p->setDigits(2);
    defineButton(d, page, "zoneReset", "Azzera zone", "Riporta le zone e il Soft Clip ai valori iniziali", zones);
}

SMToneControls readToneControls(OFX::ImageEffect& e, double time)
{
    SMToneControls c = sm_tone_defaults();
    for (const ToneSlider& t : kToneSliders) c.*(t.field) = e.fetchDoubleParam(t.name)->getValueAtTime(time);
    const ZoneValues z = readZoneValues(e, "zone", time);
    c.zonePivot = z.pivot;
    for (int i = 0; i < kZoneCount; ++i) {
        c.zoneExp[i] = z.exp[i];
        c.zoneSat[i] = z.sat[i];
        c.zoneRange[i] = z.range[i];
        c.zoneFalloff[i] = z.falloff[i];
    }
    c.softClip = e.fetchBooleanParam("softClip")->getValueAtTime(time) ? 1 : 0;
    c.softClipLevel = e.fetchDoubleParam("softClipLevel")->getValueAtTime(time);
    c.softClipColor = e.fetchDoubleParam("softClipColor")->getValueAtTime(time);
    return c;
}

std::vector<std::string> toneParamNames()
{
    std::vector<std::string> names;
    for (const ToneSlider& t : kToneSliders) names.push_back(t.name);
    names.push_back("zonePivot");
    static const char* const fields[] = { "Exp", "Sat", "Range", "Falloff" };
    for (int z = 0; z < kZoneCount; ++z)
        for (const char* f : fields) names.push_back(zoneParamName("zone", z, f));
    for (const char* s : kSoftClip) names.push_back(s);
    return names;
}

static void resetDouble(OFX::ImageEffect& e, const char* name, double value)
{
    OFX::DoubleParam* p = e.fetchDoubleParam(name);
    p->deleteAllKeys();
    p->setValue(value);
}

void resetTones(OFX::ImageEffect& e)
{
    for (const ToneSlider& t : kToneSliders) resetDouble(e, t.name, 0.0);
    clearLegacyTones(e);
}

void resetZones(OFX::ImageEffect& e)
{
    resetZoneParams(e, "zone");
    e.fetchBooleanParam("softClip")->setValue(false);
    resetDouble(e, "softClipColor", 0.0);
}

static const char* const kLegacy[][2] = { { "highlights", "H" }, { "shadows", "S" }, { "contrast", "C" },
                                          { "saturation", "Sat" }, { "colorBoost", "Boost" },
                                          { "colorRecovery", "Recovery" } };

void defineLegacyTones(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page)
{
    for (const auto& l : kLegacy) {
        if (!claimName(l[0])) continue;
        OFX::DoubleParamDescriptor* p = d.defineDoubleParam(l[0]);
        p->setDefault(0);
        p->setRange(-100, 100);
        p->setIsSecret(true);
        page->addChild(*p);
    }
}

void fetchLegacyTones(OFX::ImageEffect& e)
{
    for (const auto& l : kLegacy) (void)e.fetchDoubleParam(l[0]);
}

std::string legacyTonesNote(OFX::ImageEffect& e)
{
    std::string list;
    for (const auto& l : kLegacy) {
        OFX::DoubleParam* p = e.fetchDoubleParam(l[0]);
        const double v = p->getValue();
        if (v == 0.0 && p->getNumKeys() == 0) continue;
        char buf[48];
        snprintf(buf, sizeof(buf), "%s %+.0f", l[1], v);
        list += (list.empty() ? "" : ", ") + std::string(buf);
    }
    return list.empty() ? "" : "Toni 1.1 azzerati (" + list + "): i nuovi toni ripartono da zero";
}

void clearLegacyTones(OFX::ImageEffect& e)
{
    for (const auto& l : kLegacy) {
        OFX::DoubleParam* p = e.fetchDoubleParam(l[0]);
        if (p->getValue() != 0.0 || p->getNumKeys() != 0) {
            p->deleteAllKeys();
            p->setValue(0.0);
        }
    }
}
