// SPDX-License-Identifier: GPL-3.0-or-later
// Panel values -> DevelopParams, the only input of the per-pixel maths.
#include "DevelopEffect.h"

#include <cstdio>

#include "ofxColour.h"
#include "../common/ColourSpaces.h"
#include "ToneParams.h"

bool DevelopEffect::buildParams(double p_Time, DevelopParams& p, std::string* p_NodeInfo, std::string* p_LevelInfo)
{
    if (!m_Ready) { p.bypass = 1; return false; }
    p = DevelopParams();

    // colour space of the image entering the node
    int nodeSpace = 0, nodeGamma = 0, input = 0;
    m_NodeInput->getValue(input);
    if (input < 0 || input >= kNodeInputCount) input = 0;
    const std::string hostCs = m_SrcClip->getPropertySet().propGetString(kOfxImageClipPropColourspace, false);
    if (input > 0) {
        nodeSpace = kNodeInputPairs[input][0];
        nodeGamma = kNodeInputPairs[input][1];
    } else if (!mapColourspace(hostCs, nodeSpace, nodeGamma)) {
        // no colour management info: nodes receive the camera encoding (DaVinci YRGB)
        const int cs = validCode(m_CamSpace->getValue(), kSpaceCount);
        const int cg = validCode(m_CamGamma->getValue(), kGammaCount);
        if (cs >= 0 && cg >= 0) { nodeSpace = cs; nodeGamma = cg; }
    }
    if (p_NodeInfo) {
        *p_NodeInfo = std::string("Ingresso nodo: ") + kSpaceNames[nodeSpace] + " / " + kGammaNames[nodeGamma]
                    + (hostCs.empty() ? "" : " (Resolve: " + hostCs + ")");
    }
    p.nodeSpace = nodeSpace;
    p.nodeGamma = nodeGamma;

    // Data level runs before the bypass: a wrong scale is a decode error of the file, worth fixing
    // even with the develop off, and on clips without metadata once "Ingresso nodo" is declared.
    int levelChoice = 0;
    m_DataLevel->getValue(levelChoice);
    const int camSpaceCode = validCode(m_CamSpace->getValue(), kSpaceCount);
    const int camGammaCode = validCode(m_CamGamma->getValue(), kGammaCount);
    const int domSpace = camSpaceCode >= 0 ? camSpaceCode : (input > 0 ? nodeSpace : -1);
    const int domGamma = camGammaCode >= 0 ? camGammaCode : (input > 0 ? nodeGamma : -1);
    int want = validCode(m_LevelRequired->getValue(), 2);
    if (want < 0 && domGamma >= 7 && domGamma <= 9) want = 1;   // S-Log curves use unscaled code values
    int have = validCode(m_LevelHost->getValue(), 2);
    if (levelChoice == 1) have = 1;
    else if (levelChoice == 2) have = 0;
    std::string levelWhy;
    if (levelChoice == 3) {
        levelWhy = "disattivata";
    } else if (want < 0 || domGamma < 0 || domSpace < 0) {
        levelWhy = "curva della clip non nota: nessuna correzione";
    } else if (have < 0) {
        levelWhy = std::string("Resolve e su Auto, il valore effettivo non e leggibile · questa curva vuole ")
                 + kLevelNames[want] + " · imposta Data Level in Attributi clip (lo fa anche lo script) "
                   "oppure dichiaralo qui sopra";
    } else if (have != want) {
        sm_set_level_fix(&p, domSpace, domGamma, have);
        char buf[320];
        snprintf(buf, sizeof(buf), "in ingresso %s, la curva vuole %s · correzione x%.6f %+.6f su %s / %s",
                 kLevelNames[have], kLevelNames[want], p.levelGain, p.levelOffset,
                 kSpaceNames[p.levelSpace], kGammaNames[p.levelGamma]);
        levelWhy = buf;
    } else {
        levelWhy = std::string("in ingresso ") + kLevelNames[have] + ": corretto, nessuna correzione";
    }
    if (p_LevelInfo) *p_LevelInfo = levelWhy;

    int decode = 1;
    m_DecodeUsing->getValueAtTime(p_Time, decode);
    // typed references are only trusted when the node knows its input: S-Log3 read as another
    // curve would turn Exposure and White Balance into non-linear moves
    const bool active = m_MetaValid->getValue() || (manualReference() && inputKnown());
    if (decode == 0 || !active) {
        p.bypass = 1;
        return false;
    }

    int cs = 0, gm = 0;
    m_ColorSpace->getValueAtTime(p_Time, cs);
    m_Gamma->getValueAtTime(p_Time, gm);
    p.outSpace = cs == 0 ? nodeSpace : cs - 1;
    p.outGamma = gm == 0 ? nodeGamma : gm - 1;
    p.convert = (p.outSpace != nodeSpace || p.outGamma != nodeGamma) ? 1 : 0;
    // the Detail node reads the timeline's encoding, not this node's: after a conversion it would misread
    if (p_NodeInfo && p.convert)
        *p_NodeInfo += std::string(" · Uscita: ") + kSpaceNames[p.outSpace] + " / " + kGammaNames[p.outGamma]
                     + " (S-Log MetaRaw Detail va messo prima di questa conversione)";

    const double shotEI = m_ShotEI->getValue();
    const double ei = m_EI->getValueAtTime(p_Time);
    p.expo = (shotEI > 0.0 && ei > 0.0) ? (float)(ei / shotEI) : 1.0f;
    sm_set_white_balance(&p, m_ShotTemp->getValue(), m_ShotTint->getValue(), m_Temp->getValueAtTime(p_Time),
                         m_Tint->getValueAtTime(p_Time));

    int fc = 0;
    if (m_FcExposure->getValue()) fc = 1;
    else if (m_FcTemperature->getValue()) fc = 2;
    else if (m_FcTint->getValue()) fc = 3;
    else if (m_FcZones->getValue()) fc = 4;
    p.fcMode = fc;
    if (fc >= 2 && !sm_fc_calibrate(&p, m_Temp->getValueAtTime(p_Time), m_Tint->getValueAtTime(p_Time)))
        p.fcMode = 0;   // degenerate basis: show the picture rather than a lie
    if (p_NodeInfo && p.fcMode != 0)
        *p_NodeInfo = std::string("FALSE COLOR ATTIVO (")
                    + (p.fcMode == 1 ? "esposizione" : p.fcMode == 2 ? "temperatura" : p.fcMode == 3 ? "tint" : "zone")
                    + ") · " + *p_NodeInfo;

    const SMToneControls tones = readToneControls(*this, p_Time);
    sm_set_tone(&p, &tones, p.outSpace, p.convert, p.expo);
    return true;
}
