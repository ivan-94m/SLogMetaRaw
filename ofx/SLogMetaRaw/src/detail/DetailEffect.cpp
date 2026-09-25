// SPDX-License-Identifier: GPL-3.0-or-later
#include "DetailEffect.h"

#include <cstdio>
#include <memory>
#include <mutex>
#include <vector>

#include "ofxColour.h"
#include "ofxsMultiThread.h"
#include "../../metal/MetalKernels.h"
#include "DetailPasses.h"
#include "../common/ClipCache.h"
#include "../common/ColourSpaces.h"
#include "../common/ImageLayout.h"
#include "../common/ZoneParams.h"

static const char* const kIntensities[] = { "localContrast", "localHighlights", "localShadows",
                                            "texture", "clarity", "dehaze" };

DetailEffect::DetailEffect(OfxImageEffectHandle p_Handle)
    : ImageEffect(p_Handle)
{
    try {
        m_DstClip = fetchClip(kOfxImageEffectOutputClipName);
        m_SrcClip = fetchClip(kOfxImageEffectSimpleSourceClipName);
        m_Info = fetchStringParam("detailInfo");
        m_NodeInput = fetchChoiceParam("nodeInput");
        m_BoundPath = fetchStringParam("boundPath");
        m_CamSpace = fetchIntParam("camSpace");
        m_CamGamma = fetchIntParam("camGamma");
        m_SettingsVersion = fetchIntParam("settingsVersion");
        m_Ready = true;
    } catch (...) {
        fprintf(stderr, "S-Log MetaRaw Detail: nodo disattivato, parametro mancante\n");
        return;
    }
    try {   // fetched here, on the main thread: a first fetch on a render thread races with the UI
        for (const char* n : kIntensities) (void)getParam(n);
        for (const char* n : { "preserveDetail", "detailRadius", "edgeThreshold", "noiseThreshold", "clarityCenter",
                               "hazeLevel", "hazeWarmth", "localWhite", "viewGain", "viewBase" })
            (void)getParam(n);
        static const char* const fields[] = { "Exp", "Range", "Falloff" };
        if (paramExists("localZonePivot")) (void)getParam("localZonePivot");
        for (int z = 0; z < kZoneCount; ++z)
            for (const char* f : fields)
                if (paramExists(zoneParamName("localZone", z, f))) (void)getParam(zoneParamName("localZone", z, f));
    } catch (...) {
    }
    try {
        if (m_SettingsVersion->getValue() == 0) m_SettingsVersion->setValue(kDetailSettingsVersion);
        syncClip();
        m_Badge.attach(*this);
    } catch (...) {
    }
}

std::string DetailEffect::sourcePath() const
{
    return getPropertySet().propGetString(kOfxImageEffectPropSrcFilePath, false);
}

void DetailEffect::syncClip()
{
    const std::string path = sourcePath();
    std::string bound;
    m_BoundPath->getValue(bound);
    std::map<std::string, std::string> record;
    int space = -1, gamma = -1;
    if (!path.empty() && readClipRecord(path, record)) cameraEncoding(record, space, gamma);
    if (m_CamSpace->getValue() != space) m_CamSpace->setValue(space);
    if (m_CamGamma->getValue() != gamma) m_CamGamma->setValue(gamma);
    if (bound != path) m_BoundPath->setValue(path);
    refreshInfo();
}

// Declared, then what Resolve reports, then the clip's camera encoding (YRGB: the node after the
// develop still receives it). An unrecognised colourspace from the host leaves the node neutral.
InputOrigin DetailEffect::resolveInput(int& space, int& gamma) const
{
    int input = 0;
    m_NodeInput->getValue(input);
    if (input > 0 && input < kNodeInputCount) {
        space = kNodeInputPairs[input][0];
        gamma = kNodeInputPairs[input][1];
        return InputOrigin::Declared;
    }
    const std::string cs = m_SrcClip->getPropertySet().propGetString(kOfxImageClipPropColourspace, false);
    if (mapColourspace(cs, space, gamma)) return InputOrigin::Host;
    if (!cs.empty()) return InputOrigin::Unknown;
    std::string bound;
    m_BoundPath->getValue(bound);
    const int camS = validCode(m_CamSpace->getValue(), kSpaceCount), camG = validCode(m_CamGamma->getValue(), kGammaCount);
    if (bound == sourcePath() && camS >= 0 && camG >= 0) {
        space = camS;
        gamma = camG;
        return InputOrigin::Camera;
    }
    space = 8;   // S-Gamut3.Cine / S-Log3: what an unmanaged YRGB timeline of Sony footage carries
    gamma = 9;
    return InputOrigin::Assumed;
}

void DetailEffect::refreshInfo()
{
    int space = 0, gamma = 0;
    const InputOrigin origin = resolveInput(space, gamma);
    std::string text = "Spaziale · escluso da Generate LUT · Ingresso: ";
    if (origin == InputOrigin::Unknown) {
        text += "non riconosciuto, nodo neutro · scegli Avanzate › Ingresso nodo";
    } else {
        static const char* const from[] = { "dichiarato", "da Resolve", "dalla clip", "presunto" };
        text += std::string(kSpaceNames[space]) + " / " + kGammaNames[gamma] + " (" + from[(int)origin] + ")";
    }
    std::string cur;
    m_Info->getValue(cur);
    if (cur != text) m_Info->setValue(text);
}

bool DetailEffect::neutralAt(double p_Time) const
{
    int space = 0, gamma = 0;
    if (resolveInput(space, gamma) == InputOrigin::Unknown) return true;
    DetailEffect* self = const_cast<DetailEffect*>(this);
    for (const char* name : kIntensities)
        if (self->fetchDoubleParam(name)->getValueAtTime(p_Time) != 0.0) return false;
    const ZoneValues z = readZoneValues(*self, "localZone", p_Time);
    for (int i = 0; i < kZoneCount; ++i)
        if (z.exp[i] != 0.0) return false;
    return !self->fetchBooleanParam("viewGain")->getValueAtTime(p_Time)
        && !self->fetchBooleanParam("viewBase")->getValueAtTime(p_Time);
}

void DetailEffect::resetAll()
{
    for (const char* name : kIntensities) {
        OFX::DoubleParam* p = fetchDoubleParam(name);
        p->deleteAllKeys();
        p->setValue(0.0);
    }
    resetZoneParams(*this, "localZone");
}

void DetailEffect::beginEdit()
{
    if (!m_Ready) return;
    try {
        syncClip();
        m_Badge.refresh(true);
    } catch (...) {
    }
}

void DetailEffect::changedClip(const OFX::InstanceChangedArgs&, const std::string& p_ClipName)
{
    if (!m_Ready) return;
    if (p_ClipName == kOfxImageEffectSimpleSourceClipName) syncClip();
    m_Badge.refresh(false);
}

void DetailEffect::changedParam(const OFX::InstanceChangedArgs&, const std::string& p_ParamName)
{
    if (!m_Ready) return;
    if (p_ParamName == "version") {
        m_Badge.clicked();
        return;
    }
    if (p_ParamName == "detailReset") resetAll();
    else if (p_ParamName == "nodeInput") refreshInfo();
    else if (p_ParamName == "viewGain" && fetchBooleanParam("viewGain")->getValue())
        fetchBooleanParam("viewBase")->setValue(false);
    else if (p_ParamName == "viewBase" && fetchBooleanParam("viewBase")->getValue())
        fetchBooleanParam("viewGain")->setValue(false);
    m_Badge.refresh(false);
}

bool DetailEffect::isIdentity(const OFX::IsIdentityArguments& p_Args, OFX::Clip*& p_IdentityClip, double& p_IdentityTime)
{
    if (m_Ready && !neutralAt(p_Args.time)) return false;
    p_IdentityClip = m_SrcClip;
    p_IdentityTime = p_Args.time;
    return true;
}

namespace {
// The host's worker threads for the CPU passes.
class HostThreads : public OFX::MultiThread::Processor
{
public:
    HostThreads(int n, const std::function<void(int, int)>& fn) : m_N(n), m_Fn(fn) {}
    void multiThreadFunction(unsigned int t, unsigned int nThreads) override
    {
        m_Fn((int)((long long)m_N * t / nThreads), (int)((long long)m_N * (t + 1) / nThreads));
    }

private:
    int m_N;
    const std::function<void(int, int)>& m_Fn;
};

// Working planes shared by every Detail node: reused between frames instead of reallocated, and at
// most kKeep sets stay allocated however many nodes the project has. A set grown for a frame much
// larger than the current one is freed, so one 8K render does not pin its memory for HD work.
class ScratchLease
{
public:
    explicit ScratchLease(size_t pixels) : m_Pixels(pixels)
    {
        std::lock_guard<std::mutex> lock(mutex());
        if (!pool().empty()) {
            m_S = std::move(pool().back());
            pool().pop_back();
        } else {
            m_S.reset(new DetailScratch());
        }
    }
    ~ScratchLease()
    {
        std::lock_guard<std::mutex> lock(mutex());
        if (pool().size() < kKeep && m_S->L0.capacity() <= 2 * m_Pixels) pool().push_back(std::move(m_S));
    }
    DetailScratch& operator*() { return *m_S; }

private:
    static const size_t kKeep = 2;
    static std::mutex& mutex() { static std::mutex m; return m; }
    static std::vector<std::unique_ptr<DetailScratch>>& pool() { static std::vector<std::unique_ptr<DetailScratch>> p; return p; }
    size_t m_Pixels;
    std::unique_ptr<DetailScratch> m_S;
};
}

SMDetailControls DetailEffect::readControls(double t)
{
    SMDetailControls c = sm_detail_defaults();
    auto d = [&](const char* name) { return fetchDoubleParam(name)->getValueAtTime(t); };
    c.localContrast = d("localContrast");
    c.localHighlights = d("localHighlights");
    c.localShadows = d("localShadows");
    c.texture = d("texture");
    c.clarity = d("clarity");
    c.dehaze = d("dehaze");
    c.preserveDetail = d("preserveDetail");
    c.detailRadius = d("detailRadius");
    c.edgeThreshold = d("edgeThreshold");
    c.noiseThreshold = d("noiseThreshold");
    c.clarityCenter = d("clarityCenter");
    c.hazeLevel = d("hazeLevel");
    c.hazeWarmth = d("hazeWarmth");
    c.localWhite = d("localWhite");
    const ZoneValues z = readZoneValues(*this, "localZone", t);
    c.zonePivot = z.pivot;
    for (int i = 0; i < kZoneCount; ++i) {
        c.zoneExp[i] = z.exp[i];
        c.zoneRange[i] = z.range[i];
        c.zoneFalloff[i] = z.falloff[i];
    }
    c.viewGain = fetchBooleanParam("viewGain")->getValueAtTime(t) ? 1 : 0;
    c.viewBase = fetchBooleanParam("viewBase")->getValueAtTime(t) ? 1 : 0;
    return c;
}

void DetailEffect::render(const OFX::RenderArguments& p_Args)
{
    if (!m_Ready) return;
    if (m_DstClip->getPixelDepth() != OFX::eBitDepthFloat || m_DstClip->getPixelComponents() != OFX::ePixelComponentRGBA)
        OFX::throwSuiteStatusException(kOfxStatErrUnsupported);
    std::unique_ptr<OFX::Image> dst(m_DstClip->fetchImage(p_Args.time));
    std::unique_ptr<OFX::Image> src(m_SrcClip->fetchImage(p_Args.time));
    if (!dst || !src) OFX::throwSuiteStatusException(kOfxStatErrValue);
    const OfxRectI b = src->getBounds();
    const int W = b.x2 - b.x1, H = b.y2 - b.y1;
    if (!sameLayout(*src, *dst)) OFX::throwSuiteStatusException(kOfxStatErrImageFormat);
    int space = 8, gamma = 9;
    resolveInput(space, gamma);
    // The whole frame arrives (no tiles), so its height is the reference of every radius: the same
    // look at full size, in proxy and in the viewer.
    const SMDetailControls controls = readControls(p_Args.time);
    DetailParams p;
    dt_prepare(&p, W, H, H, src->getPixelAspectRatio(), space, gamma, &controls, SM_DT_GRID_BASE);
#ifdef __APPLE__
    if (p_Args.isEnabledMetalRender) {
        if (!RunDetailKernels(p_Args.pMetalCmdQ, p, src->getRowBytes() / 16, static_cast<const float*>(src->getPixelData()),
                              static_cast<float*>(dst->getPixelData())))
            OFX::throwSuiteStatusException(kOfxStatFailed);
        return;
    }
#endif
    Parallel parallel = [](int n, const std::function<void(int, int)>& fn) {
        HostThreads threads(n, fn);
        threads.multiThread();
    };
    ScratchLease scratch((size_t)p.W * p.H);
    detailRenderCPU(p, static_cast<const float*>(src->getPixelData()), (size_t)src->getRowBytes() / 4,
                    static_cast<float*>(dst->getPixelData()), (size_t)dst->getRowBytes() / 4, parallel, *scratch);
}
