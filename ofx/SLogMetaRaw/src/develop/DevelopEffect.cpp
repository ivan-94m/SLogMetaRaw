// SPDX-License-Identifier: GPL-3.0-or-later
#include "DevelopEffect.h"

#include <cmath>
#include <cstdio>
#include <memory>

#include "DevelopProcessor.h"
#include "../common/ImageLayout.h"
#include "ToneParams.h"

const double kPresetKelvin[] = { 0.0, 5600.0, 6500.0, 7500.0, 3200.0, 4000.0, 5500.0 };

DevelopEffect::DevelopEffect(OfxImageEffectHandle p_Handle)
    : ImageEffect(p_Handle)
{
    // A missing parameter must never throw back into the host: the node disables itself instead.
    try {
        m_DstClip = fetchClip(kOfxImageEffectOutputClipName);
        m_SrcClip = fetchClip(kOfxImageEffectSimpleSourceClipName);
        m_Camera = fetchStringParam("camera");
        for (int i = 0; i < kDetailCount; ++i) m_Details[i] = fetchStringParam(kDetails[i].param);
        m_Status = fetchStringParam("status");
        m_DecodeUsing = fetchChoiceParam("decodeUsing");
        m_WBMode = fetchChoiceParam("whiteBalance");
        m_ColorSpace = fetchChoiceParam("colorSpace");
        m_Gamma = fetchChoiceParam("gamma");
        m_Temp = fetchDoubleParam("colorTemp");
        m_Tint = fetchDoubleParam("tint");
        m_EI = fetchDoubleParam("exposure");
        m_FcExposure = fetchBooleanParam("fcExposure");
        m_FcTemperature = fetchBooleanParam("fcTemperature");
        m_FcTint = fetchBooleanParam("fcTint");
        m_FcZones = fetchBooleanParam("fcZones");
        for (const std::string& name : toneParamNames()) (void)getParam(name);   // all present, or not ready
        m_NodeInput = fetchChoiceParam("nodeInput");
        m_NodeInfo = fetchStringParam("nodeInfo");
        m_DataLevel = fetchChoiceParam("dataLevel");
        m_LevelInfo = fetchStringParam("levelInfo");
        m_BoundPath = fetchStringParam("boundPath");
        m_ShotTemp = fetchDoubleParam("shotTemp");
        m_ShotTint = fetchDoubleParam("shotTint");
        m_ShotEI = fetchDoubleParam("shotEI");
        m_CamSpace = fetchIntParam("camSpace");
        m_CamGamma = fetchIntParam("camGamma");
        m_LevelRequired = fetchIntParam("levelRequired");
        m_LevelHost = fetchIntParam("levelHost");
        m_MetaValid = fetchBooleanParam("metaValid");
        m_Unlock = fetchBooleanParam("unlockNoMeta");
        m_RefSource = fetchIntParam("refSource");
        m_SettingsVersion = fetchIntParam("settingsVersion");
        m_Ready = true;
    } catch (const std::exception& e) {
        fprintf(stderr, "S-Log MetaRaw: nodo disattivato, parametro mancante (%s)\n", e.what());
        return;
    } catch (...) {
        fprintf(stderr, "S-Log MetaRaw: nodo disattivato, parametro mancante\n");
        return;
    }
    m_RefEI = m_ShotEI->getValue();
    try {
        fetchLegacyTones(*this);
    } catch (...) {
    }
    // Some hosts refuse parameter changes while an instance is being created; beginEdit retries.
    // Only the cache here: opening a project must never wait for a reader per node.
    try {
        migrateSettings();
        syncMetadata(MetaMode::CacheOnly);
        m_Badge.attach(*this);
    } catch (...) {
    }
}

std::string DevelopEffect::sourcePath() const
{
    return getPropertySet().propGetString(kOfxImageEffectPropSrcFilePath, false);
}

void DevelopEffect::beginEdit()
{
    if (!m_Ready) return;
    try {
        migrateSettings();
        syncMetadata(MetaMode::Read);
        m_Badge.refresh(true);
    } catch (...) {
    }
}

void DevelopEffect::changedClip(const OFX::InstanceChangedArgs&, const std::string& p_ClipName)
{
    if (!m_Ready) return;
    if (p_ClipName == kOfxImageEffectSimpleSourceClipName) syncMetadata(MetaMode::Read);
    m_Badge.refresh(false);
}

void DevelopEffect::changedParam(const OFX::InstanceChangedArgs& p_Args, const std::string& p_ParamName)
{
    if (!m_Ready) return;
    const bool user = (p_Args.reason == OFX::eChangeUserEdit);
    if (p_ParamName == "reload") {
        syncMetadata(MetaMode::Reload);
    } else if (p_ParamName == "version") {
        m_Badge.clicked();
    } else if (p_ParamName == "unlockNoMeta" && user) {
        onUnlockChanged();
    } else if ((p_ParamName == "shotEI" || p_ParamName == "shotTemp" || p_ParamName == "shotTint") && user) {
        onReferenceChanged(p_ParamName);
    } else if (p_ParamName == "decodeUsing") {
        updateEnabledness();
    } else if (p_ParamName == "nodeInput" || p_ParamName == "dataLevel") {
        updateEnabledness();
        refreshNodeInfo();
    } else if (p_ParamName == "fcExposure" || p_ParamName == "fcTemperature" || p_ParamName == "fcTint"
               || p_ParamName == "fcZones") {
        if (user) {   // the views measure different things: only one can be on
            OFX::BooleanParam* const toggles[] = { m_FcExposure, m_FcTemperature, m_FcTint, m_FcZones };
            static const char* const names[] = { "fcExposure", "fcTemperature", "fcTint", "fcZones" };
            for (int i = 0; i < 4; ++i)
                if (p_ParamName != names[i] && toggles[i]->getValue()) toggles[i]->setValue(false);
        }
        refreshNodeInfo();
    } else if (p_ParamName == "toneReset") {
        resetTones(*this);
        m_LegacyNote.clear();
        refreshNodeInfo();
    } else if (p_ParamName == "zoneReset") {
        resetZones(*this);
    } else if (user && !m_LegacyNote.empty() && p_ParamName.compare(0, 4, "tone") == 0) {
        clearLegacyTones(*this);   // the first edit of the new tones retires the 1.1 values and their note
        m_LegacyNote.clear();
        refreshNodeInfo();
    } else if (p_ParamName == "whiteBalance" && user) {
        int wb = 0;
        m_WBMode->getValue(wb);
        if (wb == 0) {
            m_Temp->setValue(m_ShotTemp->getValue());
            m_Tint->setValue(m_ShotTint->getValue());
        } else if (wb > 0 && wb < kWBCustom) {
            m_Temp->setValue(kPresetKelvin[wb]);
            m_Tint->setValue(0.0);
        }
    } else if ((p_ParamName == "colorTemp" || p_ParamName == "tint") && user) {
        int wb = 0;
        m_WBMode->getValue(wb);
        if (wb != kWBCustom) m_WBMode->setValue(kWBCustom);   // like Camera Raw: moving a slider means Custom
    }
    if (p_ParamName != "version") m_Badge.refresh(false);
}

bool DevelopEffect::isIdentity(const OFX::IsIdentityArguments& p_Args, OFX::Clip*& p_IdentityClip, double& p_IdentityTime)
{
    if (!m_Ready) {
        p_IdentityClip = m_SrcClip;
        p_IdentityTime = p_Args.time;
        return true;
    }
    DevelopParams p;
    buildParams(p_Args.time, p);
    const bool neutral = p.levelFix == 0 && p.fcMode == 0
                         && (p.bypass || (p.convert == 0 && std::fabs(p.expo - 1.0f) < 1e-6f
                         && std::fabs(p.ratioL - 1.0f) < 1e-6f && std::fabs(p.ratioM - 1.0f) < 1e-6f
                         && std::fabs(p.ratioS - 1.0f) < 1e-6f
                         && p.toneOn == 0 && p.colorOn == 0 && p.curve.roofOn == 0));
    if (neutral) {
        p_IdentityClip = m_SrcClip;
        p_IdentityTime = p_Args.time;
    }
    return neutral;
}

void DevelopEffect::render(const OFX::RenderArguments& p_Args)
{
    if (!m_Ready || !m_DstClip || !m_SrcClip) return;
    if (m_DstClip->getPixelDepth() != OFX::eBitDepthFloat || m_DstClip->getPixelComponents() != OFX::ePixelComponentRGBA)
        OFX::throwSuiteStatusException(kOfxStatErrUnsupported);
    std::unique_ptr<OFX::Image> dst(m_DstClip->fetchImage(p_Args.time));
    std::unique_ptr<OFX::Image> src(m_SrcClip->fetchImage(p_Args.time));
    if (!dst || !src) OFX::throwSuiteStatusException(kOfxStatErrValue);
    if (src->getPixelDepth() != dst->getPixelDepth() || src->getPixelComponents() != dst->getPixelComponents())
        OFX::throwSuiteStatusException(kOfxStatErrValue);
    // the Metal kernel walks dst with the src geometry; the CPU path addresses each image on its own
#ifdef __APPLE__
    if (p_Args.isEnabledMetalRender && !sameLayout(*src, *dst)) OFX::throwSuiteStatusException(kOfxStatErrImageFormat);
#endif
    DevelopParams params;
    buildParams(p_Args.time, params);
    DevelopProcessor processor(*this);
    processor.setDstImg(dst.get());
    processor.setSrcImg(src.get());
    processor.setGPURenderArgs(p_Args);
    processor.setRenderWindow(p_Args.renderWindow);
    processor.setParams(params);
    processor.process();
    if (processor.failed()) OFX::throwSuiteStatusException(kOfxStatFailed);
}
