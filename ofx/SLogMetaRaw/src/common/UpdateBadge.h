// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "ofxsImageEffect.h"

// The "version" button at the top of both panels. Call only from OFX actions (UI thread).
class UpdateBadge
{
public:
    void attach(OFX::ImageEffect& effect);   // fetches the button and starts the automatic check
    void refresh(bool force);                // applies the label when the check has news
    void clicked();

private:
    OFX::PushButtonParam* m_Button = nullptr;
    unsigned m_Seen = ~0u;
};

void defineVersionButton(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page);
