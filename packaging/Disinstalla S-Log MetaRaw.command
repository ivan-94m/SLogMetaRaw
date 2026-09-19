#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Removes S-Log MetaRaw (script, library, SLogMetaRaw plugin). Your clips and projects are not touched.
echo "Disinstallazione di S-Log MetaRaw (serve la password di amministratore)."
read -r -p "Continuare? [s/N] " ok
[[ "$ok" == "s" || "$ok" == "S" ]] || exit 0
SCRIPTS="Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
sudo rm -rf "/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle" "/Library/OFX/Plugins/SonyMetaRAW.ofx.bundle" \
            "/Library/Application Support/SLogMetaRaw" "/Library/Application Support/SonyMeta" \
            "/$SCRIPTS/S-Log MetaRaw.py" "/$SCRIPTS/SLogMetaRaw.py" "/$SCRIPTS/SonyMeta.py"
rm -f "$HOME/$SCRIPTS/S-Log MetaRaw.py" "$HOME/$SCRIPTS/SLogMetaRaw.py" "$HOME/$SCRIPTS/SonyMeta.py"
rm -rf "$HOME/Library/Application Support/SLogMetaRaw" "$HOME/Library/Application Support/SonyMeta"
sudo pkgutil --forget com.slogmetaraw.pkg >/dev/null 2>&1
sudo pkgutil --forget com.sonymeta.pkg >/dev/null 2>&1
echo "S-Log MetaRaw rimosso. Riavvia DaVinci Resolve."
