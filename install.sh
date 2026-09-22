#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs S-Log MetaRaw into DaVinci Resolve (current user).
#   ./install.sh         copy the library to ~/Library/Application Support/SLogMetaRaw
#   ./install.sh --dev   point Resolve at this working copy (for development)
#   ./install.sh --dev --script-only   update the script without touching OpenFX
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEV=0
SCRIPT_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --dev) DEV=1 ;;
    --script-only) SCRIPT_ONLY=1 ;;
    --help|-h)
      echo "Usage: $0 [--dev] [--script-only]"
      echo "  --dev          use this working copy instead of copying the library"
      echo "  --script-only  install script and library; leave the OpenFX plugin untouched"
      exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done
# Resolve 21.1 includes Python; no separate installation is needed to render the launcher.
PYTHON_BIN="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Applications/ResolvePython"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERRORE: Python 3 non trovato. Installa DaVinci Resolve 21.1 o Python 3." >&2
  exit 1
fi
SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
if [[ "$DEV" == 1 ]]; then
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
"$PYTHON_BIN" "$HERE/tools/render_launcher.py" "$HERE/resolve_script/SLogMetaRaw.py" \
  "$LIB" "$SCRIPTS/S-Log MetaRaw.py"
rm -f "$SCRIPTS/SonyMeta.py" "$SCRIPTS/SLogMetaRaw.py"   # older names, avoid duplicate menu entries
# where the SLogMetaRaw plugin finds the library when it has to read a clip by itself
mkdir -p "$HOME/Library/Application Support/SLogMetaRaw/cache"
printf '%s\n' "$LIB" > "$HOME/Library/Application Support/SLogMetaRaw/lib_path"

# SLogMetaRaw OpenFX plugin (needs administrator rights for /Library/OFX/Plugins)
BUNDLE="$HERE/ofx/SLogMetaRaw/SLogMetaRaw.ofx.bundle"
if [[ "$SCRIPT_ONLY" == 1 ]]; then
  echo "Script e libreria aggiornati; plugin OpenFX lasciato invariato."
elif [[ -d "$BUNDLE" ]]; then
  echo "Installo il plugin SLogMetaRaw in /Library/OFX/Plugins (serve la password di amministratore)..."
  sudo rm -rf "/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle"
  sudo mkdir -p /Library/OFX/Plugins
  if [[ "$DEV" == 1 ]]; then
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
