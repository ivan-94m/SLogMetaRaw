// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>

#include "ofxsImageEffect.h"

#include "../../gen/DevelopMath.h"
#include "../common/UpdateBadge.h"

const int kDetailSettingsVersion = 1;

// Where the input encoding came from, shown in the info line.
enum class InputOrigin { Declared, Host, Camera, Assumed, Unknown };

class DetailEffect : public OFX::ImageEffect
{
public:
    explicit DetailEffect(OfxImageEffectHandle p_Handle);

    void render(const OFX::RenderArguments& p_Args) override;
    bool isIdentity(const OFX::IsIdentityArguments& p_Args, OFX::Clip*& p_IdentityClip, double& p_IdentityTime) override;
    void changedParam(const OFX::InstanceChangedArgs& p_Args, const std::string& p_ParamName) override;
    void changedClip(const OFX::InstanceChangedArgs& p_Args, const std::string& p_ClipName) override;
    void beginEdit() override;

private:
    std::string sourcePath() const;
    void syncClip();                                  // camera encoding of the clip, from the cache only
    InputOrigin resolveInput(int& space, int& gamma) const;
    bool neutralAt(double p_Time) const;
    SMDetailControls readControls(double p_Time);
    void refreshInfo();
    void resetAll();

    bool m_Ready = false;
    UpdateBadge m_Badge;
    OFX::Clip* m_DstClip = nullptr;
    OFX::Clip* m_SrcClip = nullptr;
    OFX::StringParam* m_Info = nullptr;
    OFX::ChoiceParam* m_NodeInput = nullptr;
    OFX::StringParam* m_BoundPath = nullptr;
    OFX::IntParam* m_CamSpace = nullptr;
    OFX::IntParam* m_CamGamma = nullptr;
    OFX::IntParam* m_SettingsVersion = nullptr;
};
