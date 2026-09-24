// SPDX-License-Identifier: GPL-3.0-or-later
#include "DevelopFactory.h"

#include "../common/ColourSpaces.h"
#include "../common/ParamDefs.h"
#include "../common/UpdateBadge.h"
#include "ClipMeta.h"
#include "DevelopEffect.h"
#include "ToneParams.h"

using namespace OFX;

DevelopFactory::DevelopFactory() : PluginFactoryHelper<DevelopFactory>(kDevelopIdentifier, 1, 4) {}

void DevelopFactory::describe(ImageEffectDescriptor& p_Desc)
{
    describeEffectCommon(p_Desc, "S-Log MetaRaw",
                         "Controlli Camera Raw (Sony Video) per clip Sony MP4: si imposta da solo con i metadata di "
                         "camera registrati da S-Log MetaRaw. Ivan Mazzone + Claude (@Ivan_94m).",
                         "com.slogmetaraw.SLogMetaRaw.png", kPointwiseLutSafe);
}

void DevelopFactory::describeInContext(ImageEffectDescriptor& d, ContextEnum)
{
    resetParamNames();
    defineClips(d);
    PageParamDescriptor* page = d.definePageParam("Controls");

    defineVersionButton(d, page);
    defineInfo(d, page, nullptr, "camera", "Camera", "— premi Rileggi metadata");
    defineButton(d, page, "reload", "Rileggi metadata",
                 "Rilegge i metadata della clip dal file, li scrive nel Media Pool di Resolve "
                 "e riporta i controlli ai valori di camera");

    // same order as the native Camera Raw "Sony Video" panel
    static const char* decodeOpts[] = { "Camera metadata", "Clip" };
    defineChoice(d, page, "decodeUsing", "Decode Using", decodeOpts, 2, 1,
                 "Camera metadata: usa i valori di ripresa e blocca i controlli. Clip: puoi modificarli");
    static const char* wbOpts[] = { "As shot", "Daylight", "Cloudy", "Shade", "Tungsten", "Fluorescent", "Flash", "Custom" };
    defineChoice(d, page, "whiteBalance", "White Balance", wbOpts, 8, 0,
                 "As shot riporta ai Kelvin di ripresa; muovendo gli slider diventa Custom");
    defineToggle(d, page, "fcTemperature", "False color: temperatura", "fc_temperature.png",
                 "Immagine in grigio, dominanti sull'asse della temperatura colorate: blu = fredda "
                 "(alza Color Temp), arancio = calda (abbassala). Muovi finche il neutro resta grigio");
    defineSlider(d, page, "colorTemp", "Color Temp", 5600, 2000, 15000, 2000, 15000, 10,
                 "Temperatura in Kelvin: adattamento cromatico Bradford in luce lineare");
    defineToggle(d, page, "fcTint", "False color: tint", "fc_tint.png",
                 "Immagine in grigio, dominanti sull'asse della tinta colorate: verde (alza Tint), "
                 "magenta (abbassalo). Muovi finche il neutro resta grigio");
    defineSlider(d, page, "tint", "Tint", 0, -100, 100, -100, 100, 0.1, "Verde/magenta, perpendicolare al luogo di Planck");
    defineToggle(d, page, "fcExposure", "False color: esposizione", "fc_exposure.png",
                 "Mappa le fermate attorno al grigio 18%: verde = grigio medio, rosa = incarnato "
                 "(una fermata sopra), giallo = vicino al clip, rosso = clip, blu e viola = nero");
    defineSlider(d, page, "exposure", "Exposure", 800, 25, 409600, 50, 25600, 1,
                 "Exposure Index: il doppio dell'EI di ripresa = +1 stop");
    static const char* csOpts[] = { "Timeline", "DaVinci WG", "Rec.709", "Rec.2020", "P3 D65", "P3 D60", "P3 DCI",
                                    "S-Gamut", "S-Gamut3", "S-Gamut3.Cine", "ACES AP0", "ACES AP1" };
    defineChoice(d, page, "colorSpace", "Color Space", csOpts, 12, 0,
                 "Gamut in uscita, come un Color Space Transform. Timeline non converte");
    static const char* gmOpts[] = { "Timeline", "DaVinci Intermediate", "Linear", "Gamma 2.2", "Gamma 2.4", "Gamma 2.6",
                                    "Rec.709", "sRGB", "SLog", "SLog2", "SLog3", "ACEScct" };
    defineChoice(d, page, "gamma", "Gamma", gmOpts, 12, 0, "Curva in uscita. Timeline non converte");

    GroupParamDescriptor* tones = defineGroup(d, page, "tonesGroup", "Toni", true);
    GroupParamDescriptor* zones = defineGroup(d, page, "zonesGroup", "Zone", false);
    defineToneParams(d, page, tones, zones);

    GroupParamDescriptor* adv = defineGroup(d, page, "advancedGroup", "Avanzate", false);
    defineChoice(d, page, "nodeInput", "Ingresso nodo", kNodeInputNames, kNodeInputCount, 0,
                 "Spazio colore che entra nel nodo. Automatico lo chiede a Resolve: cambialo solo se sbagliato", adv);
    defineInfo(d, page, adv, "nodeInfo", "Rilevato");
    static const char* levelOpts[] = { "Automatico", "Full (0-1023)", "Video (64-940)", "Nessuna correzione" };
    defineChoice(d, page, "dataLevel", "Data level in ingresso", levelOpts, 4, 0,
                 "Scala di code value su cui Resolve ha decodificato la clip. Automatico usa l'attributo "
                 "Data Level della clip: se e su Auto non correggo niente. Full o Video lo dichiari tu, "
                 "utile su un ProRes esterno che nessun NLE segnala", adv);
    defineInfo(d, page, adv, "levelInfo", "Data level");
    defineCheck(d, page, "unlockNoMeta", "Sblocca controlli senza metadata", false,
                "Quando i metadata della clip mancano o non si leggono (registratori esterni, ProRes, clip lunghe): "
                "attiva i controlli sui riferimenti di ripresa qui sotto", adv);
    // Named shot* since 1.0 (Resolve restores by name): the camera values, or the ones typed here.
    const char* refHint = "Riferimento di ripresa: cambia lo zero di Exposure e Color Temp, non l'immagine. "
                          "Con White Balance su Custom i valori restano";
    DoubleParamDescriptor* refs[] = {
        defineSlider(d, page, "shotEI", "EI di ripresa", 800, 25, 409600, 100, 25600, 1, refHint, adv),
        defineSlider(d, page, "shotTemp", "Kelvin di ripresa", 5600, 2000, 15000, 2000, 15000, 10, refHint, adv),
        defineSlider(d, page, "shotTint", "Tint di ripresa", 0, -100, 100, -100, 100, 0.1, refHint, adv) };
    for (DoubleParamDescriptor* r : refs) {
        if (!r) continue;
        r->setAnimates(false);
        r->setIsSecret(true);   // shown when the box above is ticked
    }
    defineInfo(d, page, adv, "status", "Stato");

    GroupParamDescriptor* details = defineGroup(d, page, "detailsGroup", "Dati di ripresa", false);
    if (details) details->setHint("Valori letti dalla clip, in sola lettura");
    for (int i = 0; i < kDetailCount; ++i) defineInfo(d, page, details, kDetails[i].param, kDetails[i].label);

    if (claimName("boundPath")) hideParam(d.defineStringParam("boundPath"), page);
    defineHiddenInt(d, page, "camSpace", -1);
    defineHiddenInt(d, page, "camGamma", -1);
    defineHiddenInt(d, page, "levelRequired", -1);
    defineHiddenInt(d, page, "levelHost", -1);
    if (claimName("metaValid")) {
        BooleanParamDescriptor* valid = d.defineBooleanParam("metaValid");
        valid->setDefault(false);
        hideParam(valid, page);
    }
    defineHiddenInt(d, page, "refSource", 0);
    defineLegacyTones(d, page);
    defineHiddenInt(d, page, "settingsVersion", 0);
}

ImageEffect* DevelopFactory::createInstance(OfxImageEffectHandle p_Handle, ContextEnum)
{
    return new DevelopEffect(p_Handle);
}
