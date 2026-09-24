// SPDX-License-Identifier: GPL-3.0-or-later
#include "UpdateBadge.h"

#include "ParamDefs.h"
#include "Update.h"

static std::string label(const Update::Snapshot& n)
{
    const std::string v = std::string("v") + Update::release();
    switch (n.kind) {
    case Update::Available: return n.opened ? "\xF0\x9F\x9F\xA2 " + n.latest + " nel browser"
                                            : "\xF0\x9F\x9F\xA2 " + v + " \xE2\x86\x92 " + n.latest;
    case Update::Installed: return v + " \xC2\xB7 riavvia Resolve";
    case Update::Checking: return n.manual ? v + " \xC2\xB7 controllo\xE2\x80\xA6" : v;
    case Update::Current: return n.manual ? v + " \xC2\xB7 aggiornato" : v;
    case Update::Failed: return n.manual ? v + " \xC2\xB7 controllo non riuscito" : v;
    default: return v;
    }
}

static std::string hint(const Update::Snapshot& n)
{
    switch (n.kind) {
    case Update::Available:
        return n.opened ? "Download di S-Log MetaRaw " + n.latest + " avviato. Installa a Resolve chiuso."
                        : "Disponibile la " + n.latest + ": clicca per scaricare"
                              + (n.title.empty() ? "" : " \xC2\xB7 " + n.title);
    case Update::Installed: return "La " + n.latest + " e installata: riavvia Resolve per usarla";
    case Update::Checking: return "Controllo in corso: l'esito compare alla prossima modifica del nodo";
    case Update::Current: return std::string("Nessuna versione piu recente (sei alla ") + Update::release() + ").";
    case Update::Failed: return n.error + " \xC2\xB7 clicca per riprovare";
    case Update::Disabled: return "Controllo automatico disattivato: clicca per controllare gli aggiornamenti";
    default: return "Clicca per controllare gli aggiornamenti";
    }
}

void UpdateBadge::attach(OFX::ImageEffect& effect)
{
    if (effect.paramExists("version")) m_Button = effect.fetchPushButtonParam("version");
    Update::start(false, OFX::getImageEffectHostDescription()->hostIsBackground);
    refresh(true);
}

void UpdateBadge::refresh(bool force)
{
    if (!m_Button) return;
    const Update::Snapshot n = Update::snapshot();
    if (!force && n.serial == m_Seen) return;
    m_Seen = n.serial;
    m_Button->setLabel(label(n));
    m_Button->setHint(hint(n));
}

void UpdateBadge::clicked()
{
    std::string error;
    if (Update::snapshot().kind == Update::Available) {
        Update::openInstaller(error);
    } else {
        Update::start(true, false);
        Update::waitManual(800);   // OpenFX has no timers: a fast answer shows at once, a slow one later
    }
    refresh(true);
}

void defineVersionButton(OFX::ImageEffectDescriptor& d, OFX::PageParamDescriptor* page)
{
    const std::string v = std::string("v") + Update::release();
    defineButton(d, page, "version", v, "Clicca per controllare gli aggiornamenti");
}
