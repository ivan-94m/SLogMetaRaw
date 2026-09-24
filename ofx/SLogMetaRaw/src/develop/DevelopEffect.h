// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>

#include "ofxsImageEffect.h"

#include "../../gen/DevelopMath.h"
#include "ClipMeta.h"
#include "../common/UpdateBadge.h"

const int kSettingsVersion = 5;   // bump when the meaning of a saved parameter changes
const int kWBCustom = 7;
extern const double kPresetKelvin[];   // index = White Balance choice

class DevelopEffect : public OFX::ImageEffect
{
public:
    explicit DevelopEffect(OfxImageEffectHandle p_Handle);

    void render(const OFX::RenderArguments& p_Args) override;
    bool isIdentity(const OFX::IsIdentityArguments& p_Args, OFX::Clip*& p_IdentityClip, double& p_IdentityTime) override;
    void changedParam(const OFX::InstanceChangedArgs& p_Args, const std::string& p_ParamName) override;
    void changedClip(const OFX::InstanceChangedArgs& p_Args, const std::string& p_ClipName) override;
    void beginEdit() override;

private:
    std::string sourcePath() const;
    bool inputKnown() const;     // the node knows what encoding enters it
    bool manualReference() const { return m_Unlock->getValue() && !m_MetaValid->getValue(); }
    // DevelopSync.cpp
    void migrateSettings();
    void syncMetadata(MetaMode p_Mode);
    void updateEnabledness();
    void refreshNodeInfo();
    void composeStatus();
    void onUnlockChanged();
    void onReferenceChanged(const std::string& p_Name);
    // BuildParams.cpp
    bool buildParams(double p_Time, DevelopParams& p_Params, std::string* p_NodeInfo = nullptr,
                     std::string* p_LevelInfo = nullptr);

    bool m_Ready = false;   // false when a parameter is missing: the node then stays transparent
    UpdateBadge m_Badge;
    // what the Camera line and Stato say, composed in one place (composeStatus)
    std::string m_CameraName, m_Detail;
    MetaOutcome m_Outcome = MetaOutcome::Missing;
    bool m_NotLog = false, m_FoundWhileManual = false;
    double m_RefEI = 800.0;      // the reference before the user's edit, to rescale Exposure
    std::string m_LegacyNote;    // 1.1 tone values that no longer apply
    OFX::Clip* m_DstClip = nullptr;
    OFX::Clip* m_SrcClip = nullptr;

    OFX::StringParam* m_Camera = nullptr;
    OFX::StringParam* m_Details[16] = {};
    OFX::StringParam* m_Status = nullptr;
    OFX::ChoiceParam* m_DecodeUsing = nullptr;
    OFX::ChoiceParam* m_WBMode = nullptr;
    OFX::ChoiceParam* m_ColorSpace = nullptr;
    OFX::ChoiceParam* m_Gamma = nullptr;
    OFX::DoubleParam* m_Temp = nullptr;
    OFX::DoubleParam* m_Tint = nullptr;
    OFX::DoubleParam* m_EI = nullptr;
    OFX::BooleanParam* m_FcExposure = nullptr;
    OFX::BooleanParam* m_FcTemperature = nullptr;
    OFX::BooleanParam* m_FcTint = nullptr;
    OFX::BooleanParam* m_FcZones = nullptr;
    OFX::ChoiceParam* m_NodeInput = nullptr;
    OFX::StringParam* m_NodeInfo = nullptr;
    OFX::ChoiceParam* m_DataLevel = nullptr;
    OFX::StringParam* m_LevelInfo = nullptr;
    // hidden, saved with the grade
    OFX::StringParam* m_BoundPath = nullptr;
    OFX::DoubleParam* m_ShotTemp = nullptr;
    OFX::DoubleParam* m_ShotTint = nullptr;
    OFX::DoubleParam* m_ShotEI = nullptr;
    OFX::IntParam* m_CamSpace = nullptr;
    OFX::IntParam* m_CamGamma = nullptr;
    OFX::IntParam* m_LevelRequired = nullptr;
    OFX::IntParam* m_LevelHost = nullptr;
    OFX::BooleanParam* m_MetaValid = nullptr;
    OFX::BooleanParam* m_Unlock = nullptr;
    OFX::IntParam* m_RefSource = nullptr;   // 0 unknown, 1 camera metadata, 2 typed by the user
    OFX::IntParam* m_SettingsVersion = nullptr;
};
