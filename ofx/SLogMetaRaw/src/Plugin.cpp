// SPDX-License-Identifier: GPL-3.0-or-later
// S-Log MetaRaw - Copyright (C) 2026 Ivan Mazzone
// Free software under the GNU General Public License v3 or later; no warranty.
#include "ofxsImageEffect.h"

#include "detail/DetailFactory.h"
#include "develop/DevelopFactory.h"

// The index of a plugin in the bundle is part of how Resolve identifies it: append, never reorder.
void OFX::Plugin::getPluginIDs(PluginFactoryArray& p_FactoryArray)
{
    static DevelopFactory develop;
    static DetailFactory detail;
    p_FactoryArray.push_back(&develop);
    p_FactoryArray.push_back(&detail);
}
