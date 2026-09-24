// SPDX-License-Identifier: GPL-3.0-or-later
#include "DetailFactory.h"

#include "../common/ColourSpaces.h"
#include "../common/ParamDefs.h"
#include "../common/UpdateBadge.h"
#include "../common/ZoneParams.h"
#include "DetailEffect.h"

using namespace OFX;

DetailFactory::DetailFactory() : PluginFactoryHelper<DetailFactory>(kDetailIdentifier, 1, 0) {}

void DetailFactory::describe(ImageEffectDescriptor& p_Desc)
{
    describeEffectCommon(p_Desc, "S-Log MetaRaw Detail",
                         "Recupero locale di luci e ombre, Texture, Clarity e Dehaze in luce di scena, dopo S-Log "
                         "MetaRaw. Spaziale: escluso da Generate LUT. Ivan Mazzone + Claude (@Ivan_94m).",
                         "com.slogmetaraw.SLogMetaRawDetail.png", kSpatial);
}

static DoubleParamDescriptor* trim(ImageEffectDescriptor& d, PageParamDescriptor* page, GroupParamDescriptor* group,
                                   const char* name, const char* label, double lo, double hi, const char* hint)
{
    DoubleParamDescriptor* p = defineSlider(d, page, name, label, 0, lo, hi, lo, hi, 0.1, hint, group);
    if (p) p->setDigits(2);
    return p;
}

void DetailFactory::describeInContext(ImageEffectDescriptor& d, ContextEnum)
{
    resetParamNames();
    defineClips(d);
    PageParamDescriptor* page = d.definePageParam("Controls");
    defineVersionButton(d, page);
    defineInfo(d, page, nullptr, "detailInfo", "Detail", "Spaziale · escluso da Generate LUT");

    GroupParamDescriptor* range = defineGroup(d, page, "rangeGroup", "Gamma dinamica", true);
    defineToggle(d, page, "viewGain", "Vista: guadagno", "view_gain.png",
                 "Mostra quanto il nodo alza (arancio) o abbassa (blu) ogni zona: grigio = invariato. "
                 "Bande a 0,25 / 0,5 / 1 / 2 stop", range);
    defineToggle(d, page, "viewBase", "Vista: base", "view_base.png",
                 "Mostra la base edge-aware su cui lavorano i toni locali, senza il dettaglio", range);
    trim(d, page, range, "localContrast", "Local Contrast", -100, 50,
         "Contrasto delle grandi aree attorno al grigio, a dettaglio intatto. Il Contrast del nodo principale e "
         "globale; qui il dettaglio fine resta com'e");
    trim(d, page, range, "localHighlights", "Local Highlights", -100, 100,
         "Negativo: comprime le grandi aree luminose e tiene, anzi rinforza, la texture (a -100 il massimo registrato "
         "arriva sul Bianco di Avanzate); le luci piu compresse vanno verso il bianco. Positivo: piu stacco per aree. "
         "Grigio e toni sotto restano fermi");
    trim(d, page, range, "localShadows", "Local Shadows", -100, 100,
         "Apre (positivo) o chiude le ombre per aree, a dettaglio intatto. 100 = 2 stop");

    GroupParamDescriptor* presence = defineGroup(d, page, "presenceGroup", "Presenza", true);
    trim(d, page, presence, "texture", "Texture", -100, 100,
         "Dettaglio fine (pelle, tessuti, foglie). Negativo leviga; la grana sotto la soglia rumore non sale");
    trim(d, page, presence, "clarity", "Clarity", -100, 100,
         "Contrasto locale a media scala, pesato sui mezzitoni");
    trim(d, page, presence, "dehaze", "Dehaze", -100, 100,
         "Toglie (positivo) o aggiunge velo. Il colore e il livello del velo sono in Avanzate › Velo, mai stimati "
         "fotogramma per fotogramma");
    defineButton(d, page, "detailReset", "Azzera dettaglio", "Riporta a zero tutti i controlli di questo nodo", presence);

    GroupParamDescriptor* zones = defineGroup(d, page, "localZonesGroup", "Zone locali", false);
    defineZoneParams(d, page, zones, "localZone", false);

    GroupParamDescriptor* adv = defineGroup(d, page, "detailAdvancedGroup", "Avanzate", false);
    if (auto* p = defineSlider(d, page, "preserveDetail", "Preserva dettaglio", 100, 0, 100, 0, 100, 1,
                               "100 = i toni locali muovono solo le aree; 0 = come il nodo principale, puntuale", adv))
        p->setDigits(0);
    defineSlider(d, page, "detailRadius", "Raggio (% altezza)", 4, 1, 8, 1, 8, 0.1,
                 "Dimensione delle aree dei toni locali, relativa all'altezza: lo stesso look a ogni risoluzione", adv);
    defineSlider(d, page, "edgeThreshold", "Soglia bordi (EV)", 0.5, 0.25, 1.0, 0.25, 1.0, 0.01,
                 "Salto di luminanza che conta come bordo: piu bassa = meno aloni, meno recupero", adv);
    defineSlider(d, page, "noiseThreshold", "Soglia rumore (EV)", 0.04, 0.0, 0.15, 0.0, 0.15, 0.005,
                 "Sotto questa ampiezza il dettaglio e trattato come rumore: Texture non lo alza. 0 = nessuna protezione",
                 adv);
    defineSlider(d, page, "clarityCenter", "Clarity: centro (EV)", 0, -3, 3, -3, 3, 0.05,
                 "Tono, in stop dal grigio 18%, dove Clarity lavora di piu", adv);
    if (auto* p = defineSlider(d, page, "localWhite", "Bianco (stop)", 2.5, 1, 10, 1, 8, 0.05,
                               "Dove Local Highlights -100 porta il massimo registrato, in stop sopra il grigio 18%. "
                               "2,5 = bianco Rec.709 con un CST senza tone mapping; con un DRT (ACES, AgX, DaVinci) "
                               "alza a 4-5", adv))
        p->setDigits(2);
    defineChoice(d, page, "nodeInput", "Ingresso nodo", kNodeInputNames, kNodeInputCount, 0,
                 "Codifica che entra nel nodo: la decodifica in luce lineare e la riscrive uguale. Automatico la chiede "
                 "a Resolve, poi alla clip. Va dopo S-Log MetaRaw e prima di CST/LUT", adv);

    GroupParamDescriptor* haze = defineGroup(d, page, "hazeGroup", "Velo", false);
    defineSlider(d, page, "hazeLevel", "Livello velo (EV)", 2, -2, 6, -2, 6, 0.05,
                 "Luminanza del velo in stop dal grigio 18%: da li in su Dehaze non agisce", haze);
    defineSlider(d, page, "hazeWarmth", "Colore velo", 0, -100, 100, -100, 100, 0.1,
                 "Negativo = velo freddo (cielo, distanza), positivo = caldo (fumo, polvere)", haze);

    if (claimName("boundPath")) hideParam(d.defineStringParam("boundPath"), page);
    defineHiddenInt(d, page, "camSpace", -1);
    defineHiddenInt(d, page, "camGamma", -1);
    defineHiddenInt(d, page, "settingsVersion", 0);
}

ImageEffect* DetailFactory::createInstance(OfxImageEffectHandle p_Handle, ContextEnum)
{
    return new DetailEffect(p_Handle);
}
