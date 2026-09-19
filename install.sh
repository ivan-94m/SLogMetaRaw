#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs S-Log MetaRaw into DaVinci Resolve (current user).
#   ./install.sh         copy the library to ~/Library/Application Support/SLogMetaRaw
#   ./install.sh --dev   point Resolve at this working copy (for development)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
if [[ "${1:-}" == "--dev" ]]; then
  LIB="$HERE"
else
  LIB="$HOME/Library/Application Support/SLogMetaRaw/lib"
  mkdir -p "$LIB"
  rm -rf "$LIB/slogmetaraw"
  cp -R "$HERE/slogmetaraw" "$LIB/"
  find "$LIB/slogmetaraw" -name '__pycache__' -prune -exec rm -rf {} +
fi
mkdir -p "$SCRIPTS"
# menu entry name in Workspace > Scripts
sed "s|__LIB_DIR__|$LIB|" "$HERE/resolve_script/SLogMetaRaw.py" > "$SCRIPTS/S-Log MetaRaw.py"
rm -f "$SCRIPTS/SonyMeta.py" "$SCRIPTS/SLogMetaRaw.py"   # older names, avoid duplicate menu entries
# where the SLogMetaRaw plugin finds the library when it has to read a clip by itself
mkdir -p "$HOME/Library/Application Support/SLogMetaRaw/cache"
printf '%s\n' "$LIB" > "$HOME/Library/Application Support/SLogMetaRaw/lib_path"

# SLogMetaRaw OpenFX plugin (needs administrator rights for /Library/OFX/Plugins)
BUNDLE="$HERE/ofx/SLogMetaRaw/SLogMetaRaw.ofx.bundle"
if [[ -d "$BUNDLE" ]]; then
  echo "Installo il plugin SLogMetaRaw in /Library/OFX/Plugins (serve la password di amministratore)..."
  sudo rm -rf "/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle"
  sudo mkdir -p /Library/OFX/Plugins
  if [[ "${1:-}" == "--dev" ]]; then
    # link to the build folder: after 'make' only a Resolve restart is needed
    sudo ln -s "$BUNDLE" /Library/OFX/Plugins/SLogMetaRaw.ofx.bundle
  else
    sudo cp -R "$BUNDLE" /Library/OFX/Plugins/
  fi
  echo "Plugin installato: riavvia DaVinci Resolve per vederlo in OpenFX > S-Log MetaRaw"
else
  echo "ATTENZIONE: plugin non compilato ($BUNDLE mancante): esegui 'make' in ofx/SLogMetaRaw"
fi
echo "Installato: $SCRIPTS/S-Log MetaRaw.py  (libreria: $LIB)"
echo "In Resolve: Workspace > Scripts > S-Log MetaRaw  (riavvia Resolve se non compare)"
