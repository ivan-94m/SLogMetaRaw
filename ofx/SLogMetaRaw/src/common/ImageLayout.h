// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "ofxsImageEffect.h"

// The kernels walk src and dst with one geometry: same bounds, same positive stride, float RGBA.
inline bool sameLayout(const OFX::Image& src, const OFX::Image& dst)
{
    const OfxRectI a = src.getBounds(), b = dst.getBounds();
    return src.getPixelDepth() == OFX::eBitDepthFloat && src.getPixelComponents() == OFX::ePixelComponentRGBA
        && dst.getPixelDepth() == OFX::eBitDepthFloat && dst.getPixelComponents() == OFX::ePixelComponentRGBA
        && a.x1 == b.x1 && a.y1 == b.y1 && a.x2 == b.x2 && a.y2 == b.y2
        && src.getRowBytes() == dst.getRowBytes() && src.getRowBytes() >= (a.x2 - a.x1) * 16;
}
