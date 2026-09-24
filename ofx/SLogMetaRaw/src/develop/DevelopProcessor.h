// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "ofxsImageEffect.h"
#include "ofxsProcessing.h"

#include "../../gen/DevelopMath.h"
#include "../../metal/MetalKernels.h"

class DevelopProcessor : public OFX::ImageProcessor
{
public:
    explicit DevelopProcessor(OFX::ImageEffect& p_Instance) : OFX::ImageProcessor(p_Instance) {}

    void processImagesMetal() override
    {
#ifdef __APPLE__
        const OfxRectI& b = _srcImg->getBounds();
        _failed = !RunDevelopKernel(_pMetalCmdQ, b.x2 - b.x1, b.y2 - b.y1, _srcImg->getRowBytes() / 16, _params,
                                    static_cast<float*>(_srcImg->getPixelData()),
                                    static_cast<float*>(_dstImg->getPixelData()));
#endif
    }

    void multiThreadProcessImages(OfxRectI p_ProcWindow) override
    {
        for (int y = p_ProcWindow.y1; y < p_ProcWindow.y2; ++y) {
            if (_effect.abort()) break;
            float* dst = static_cast<float*>(_dstImg->getPixelAddress(p_ProcWindow.x1, y));
            for (int x = p_ProcWindow.x1; x < p_ProcWindow.x2; ++x, dst += 4) {
                const float* src = static_cast<const float*>(_srcImg ? _srcImg->getPixelAddress(x, y) : nullptr);
                if (src) {
                    SMf3 o = sm_develop(smf3(src[0], src[1], src[2]), _params);
                    dst[0] = o.x; dst[1] = o.y; dst[2] = o.z; dst[3] = src[3];
                } else {
                    dst[0] = dst[1] = dst[2] = dst[3] = 0.0f;
                }
            }
        }
    }

    void setSrcImg(OFX::Image* p_Src) { _srcImg = p_Src; }
    void setParams(const DevelopParams& p) { _params = p; }
    bool failed() const { return _failed; }

private:
    OFX::Image* _srcImg = nullptr;
    DevelopParams _params = {};
    bool _failed = false;
};
