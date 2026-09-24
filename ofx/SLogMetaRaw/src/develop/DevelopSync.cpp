// SPDX-License-Identifier: GPL-3.0-or-later
// Settings migration, the link between the node and the clip's camera metadata, and the
// references typed by hand when there is none.
#include "DevelopEffect.h"

#include <cstdio>

#include "ofxColour.h"
#include "ToneParams.h"
#include "../common/ColourSpaces.h"

static void setText(OFX::StringParam* p, const std::string& v)
{
    std::string cur;
    p->getValue(cur);
    if (cur != v) p->setValue(v);   // do not touch the grade when nothing changed
}

template <typename P, typename V>
static void setIfDifferent(P* p, V v)
{
    if (p->getValue() != v) p->setValue(v);
}

// settingsVersion says which meaning the saved values had; history in RELEASE_NOTES.md.
// 0 is a new node (or a value the host did not save): treated as current.
void DevelopEffect::migrateSettings()
{
    // refSource is newer than the settings versions: a node that already read its clip is camera-referenced
    if (m_RefSource->getValue() == 0 && m_MetaValid->getValue()) m_RefSource->setValue(1);
    m_LegacyNote = legacyTonesNote(*this);
    const int saved = m_SettingsVersion->getValue();
    if (saved == kSettingsVersion) return;
    if (saved > kSettingsVersion) {   // saved by a newer plugin: keep the values as they are
        fprintf(stderr, "S-Log MetaRaw: nodo salvato con impostazioni v%d, questo plugin arriva alla v%d\n",
                saved, kSettingsVersion);
        return;
    }
    if (saved == 1) m_DataLevel->setValue(3);   // the data level correction starts off on a 1.0 grade
    m_SettingsVersion->setValue(kSettingsVersion);
}

bool DevelopEffect::inputKnown() const
{
    int input = 0, space = 0, gamma = 0;
    m_NodeInput->getValue(input);
    if (input > 0) return true;
    if (mapColourspace(m_SrcClip->getPropertySet().propGetString(kOfxImageClipPropColourspace, false), space, gamma))
        return true;
    return m_CamSpace->getValue() >= 0 && m_CamGamma->getValue() >= 0;
}

// The sliders take the camera values only for a new node, a node moved to another clip, or
// "Rileggi metadata": the colourist's adjustments survive a project reload.
void DevelopEffect::syncMetadata(MetaMode p_Mode)
{
    const std::string path = sourcePath();
    m_FoundWhileManual = false;
    m_NotLog = false;
    if (path.empty()) {
        m_Outcome = MetaOutcome::Missing;
        m_CameraName.clear();
        m_Detail = "Resolve non ha fornito il percorso della clip (compound clip?)";
        updateEnabledness();
        refreshNodeInfo();
        return;
    }
    std::string bound;
    m_BoundPath->getValue(bound);
    const bool sameClip = (bound == path);

    ClipMeta meta;
    m_Outcome = acquireMeta(path, p_Mode, meta, m_Detail);
    if (m_Outcome != MetaOutcome::Found) {
        setIfDifferent(m_MetaValid, false);
        m_CameraName.clear();
        for (int i = 0; i < kDetailCount; ++i) setText(m_Details[i], "—");
        setText(m_Details[kDetailCount - 1], path.substr(path.find_last_of('/') + 1));
        if (!sameClip) {   // decoding facts of another clip must not follow a copied node
            setIfDifferent(m_CamSpace, -1);
            setIfDifferent(m_CamGamma, -1);
            setIfDifferent(m_LevelRequired, -1);
            setIfDifferent(m_LevelHost, -1);
        }
        if (m_Unlock->getValue()) setIfDifferent(m_RefSource, 2);
        updateEnabledness();
        refreshNodeInfo();
        return;
    }

    m_CameraName = meta.fields["camera_name"];
    for (int i = 0; i < kDetailCount; ++i) {
        auto it = meta.fields.find(kDetails[i].key);
        setText(m_Details[i], it != meta.fields.end() && !it->second.empty() ? it->second : "—");
    }
    const std::string note = meta.resolveNote.empty() ? "" : " · " + meta.resolveNote;
    if (m_RefSource->getValue() == 2 && sameClip && p_Mode != MetaMode::Reload && meta.supported) {
        // references typed by hand stay until the colourist asks for the camera ones
        m_FoundWhileManual = true;
        m_Detail = "Metadata ora disponibili (EI " + std::to_string((int)meta.shotEI) + " · "
                 + std::to_string((int)meta.shotTemp) + " K): premi Rileggi metadata per usarli";
        updateEnabledness();
        refreshNodeInfo();
        return;
    }
    const bool firstRead = m_RefSource->getValue() == 0;
    setIfDifferent(m_ShotTemp, meta.shotTemp);
    setIfDifferent(m_ShotTint, meta.shotTint);
    setIfDifferent(m_ShotEI, meta.shotEI);
    setIfDifferent(m_CamSpace, meta.camSpace);
    setIfDifferent(m_CamGamma, meta.camGamma);
    setIfDifferent(m_LevelRequired, meta.levelRequired);
    setIfDifferent(m_LevelHost, meta.levelHost);
    setIfDifferent(m_RefSource, 1);
    m_RefEI = meta.shotEI;
    if (!meta.supported) {
        m_NotLog = true;
        setIfDifferent(m_MetaValid, false);
        m_Detail = "Profilo " + (meta.colorSpace.empty() ? std::string("non riconosciuto") : meta.colorSpace)
                 + " non logaritmico: il nodo resta neutro" + note;
    } else {
        setIfDifferent(m_MetaValid, true);
        m_Detail += (meta.wbEstimated ? " · Kelvin stimato (la camera non lo registra)" : "") + note;
        if (!sameClip || p_Mode == MetaMode::Reload || firstRead) {
            m_WBMode->setValue(0);
            m_Temp->setValue(meta.shotTemp);
            m_Tint->setValue(meta.shotTint);
            m_EI->setValue(meta.shotEI);
        }
    }
    if (!sameClip) m_BoundPath->setValue(path);   // only after a successful read
    updateEnabledness();
    refreshNodeInfo();
}

// The Camera line is the one status always in sight; Stato (Avanzate) carries the detail.
void DevelopEffect::composeStatus()
{
    const bool unlock = m_Unlock->getValue(), manual = manualReference();
    std::string camera;
    if (manual && !inputKnown()) camera = "Ingresso non noto · Avanzate › Ingresso nodo";
    else if (m_FoundWhileManual) camera = m_CameraName + " · Metadata trovati: Rileggi li adotta";
    else if (m_Outcome == MetaOutcome::Pending) camera = "Lettura metadata in corso…";
    else if (m_NotLog) camera = m_CameraName + " · profilo non log: nodo neutro";
    else if (m_Outcome != MetaOutcome::Found && manual) camera = "Metadata non trovati · sbloccato";
    else if (m_Outcome != MetaOutcome::Found) camera = unlock ? "Metadata non trovati"
                                                              : "Metadata non trovati · Avanzate › Sblocca controlli senza metadata";
    else camera = m_CameraName;
    setText(m_Camera, camera);

    std::string detail = m_Detail;
    if (!m_LegacyNote.empty()) detail = m_LegacyNote + (detail.empty() ? "" : " · " + detail);
    if (manual) {
        char buf[160];
        snprintf(buf, sizeof(buf), "Controlli sbloccati senza metadata · riferimento EI %g · %g K · tint %g",
                 m_ShotEI->getValue(), m_ShotTemp->getValue(), m_ShotTint->getValue());
        detail = std::string(buf) + (detail.empty() ? "" : " · " + detail);
    }
    setText(m_Status, detail);
}

void DevelopEffect::refreshNodeInfo()
{
    DevelopParams p;
    std::string info, level;
    buildParams(0.0, p, &info, &level);
    if (!info.empty()) setText(m_NodeInfo, info);
    if (!level.empty()) setText(m_LevelInfo, level);
    composeStatus();
}

void DevelopEffect::updateEnabledness()
{
    int decode = 1;
    m_DecodeUsing->getValue(decode);
    const bool manual = manualReference();
    const bool on = (decode == 1) && (m_MetaValid->getValue() || (manual && inputKnown()));
    OFX::ValueParam* const controls[] = { m_WBMode, m_ColorSpace, m_Gamma, m_Temp, m_Tint, m_EI };
    for (OFX::ValueParam* c : controls) c->setEnabled(on);
    for (const std::string& name : toneParamNames()) getParam(name)->setEnabled(on);
    OFX::DoubleParam* const refs[] = { m_ShotEI, m_ShotTemp, m_ShotTint };
    for (OFX::DoubleParam* r : refs) {
        r->setIsSecret(!m_Unlock->getValue());
        r->setEnabled(manual);
    }
}

// Ticked with no metadata: the node starts neutral on the typed references.
void DevelopEffect::onUnlockChanged()
{
    if (m_Unlock->getValue() && !m_MetaValid->getValue()) {
        m_RefSource->setValue(2);
        m_WBMode->setValue(0);
        m_EI->setValue(m_ShotEI->getValue());
        m_Temp->setValue(m_ShotTemp->getValue());
        m_Tint->setValue(m_ShotTint->getValue());
    }
    m_RefEI = m_ShotEI->getValue();
    updateEnabledness();
    refreshNodeInfo();
}

// A reference changes the numbers, not the picture: Exposure follows the EI, keys included.
void DevelopEffect::onReferenceChanged(const std::string& p_Name)
{
    if (p_Name == "shotEI") {
        const double now = m_ShotEI->getValue();
        const double ratio = m_RefEI > 0.0 ? now / m_RefEI : 1.0;
        m_RefEI = now;
        if (!manualReference() || ratio == 1.0) return;
        auto clampEI = [](double v) { return v < 25.0 ? 25.0 : (v > 409600.0 ? 409600.0 : v); };
        const unsigned keys = m_EI->getNumKeys();
        if (keys == 0) {
            m_EI->setValue(clampEI(m_EI->getValue() * ratio));
        } else {
            for (unsigned i = 0; i < keys; ++i) {
                const double t = m_EI->getKeyTime((int)i);
                m_EI->setValueAtTime(t, clampEI(m_EI->getValueAtTime(t) * ratio));
            }
        }
    } else if (manualReference()) {
        int wb = 0;
        m_WBMode->getValue(wb);
        if (wb == 0) {   // As shot follows its reference; a Custom balance keeps its numbers
            m_Temp->setValue(m_ShotTemp->getValue());
            m_Tint->setValue(m_ShotTint->getValue());
        }
    }
    refreshNodeInfo();
}
