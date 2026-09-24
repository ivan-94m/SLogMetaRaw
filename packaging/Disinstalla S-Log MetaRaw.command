#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Removes every S-Log MetaRaw installed on this Mac - 2.x, 1.x, the old SonyMeta name, developer installs, the
# test probe: plugin, library, menu script, installer receipts, and this user's cache, settings and logs. Clips,
# projects and the metadata already written into Resolve projects are not touched; CSV exports only if asked.
#   --dry-run   list what would be removed and remove nothing
# Tests only: SLOGMETARAW_ROOT (prefix of the system paths), SLOGMETARAW_YES=1 (no questions; CSV kept unless
# SLOGMETARAW_DELETE_CSV=1), SLOGMETARAW_NO_SUDO=1, SLOGMETARAW_IGNORE_RESOLVE=1.
ROOT="${SLOGMETARAW_ROOT:-}"
YES="${SLOGMETARAW_YES:-0}"
SUDO=sudo
[[ "${SLOGMETARAW_NO_SUDO:-0}" == 1 ]] && SUDO=
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

UTIL="Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
SYSTEM=(
  "$ROOT/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle"
  "$ROOT/Library/OFX/Plugins/SLogMetaRawProbe.ofx.bundle"
  "$ROOT/Library/OFX/Plugins/SonyMetaRAW.ofx.bundle"
  "$ROOT/Library/Application Support/SLogMetaRaw"
  "$ROOT/Library/Application Support/SonyMeta"
  "$ROOT/$UTIL/S-Log MetaRaw.py"
  "$ROOT/$UTIL/SLogMetaRaw.py"
  "$ROOT/$UTIL/SonyMeta.py"
)
USERS=(
  "$HOME/$UTIL/S-Log MetaRaw.py"
  "$HOME/$UTIL/SLogMetaRaw.py"
  "$HOME/$UTIL/SonyMeta.py"
  "$HOME/Library/Application Support/SLogMetaRaw"
  "$HOME/Library/Application Support/SonyMeta"
  "$HOME/Library/Logs/SLogMetaRaw"
  "$HOME/Library/Logs/SonyMeta"
  # Resolve's cache of every plugin's panel: it rebuilds it on the next start, without the removed nodes
  "$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/OFXPluginCacheV2.xml"
)
CSV="$HOME/Documents/SLogMetaRaw"
RECEIPTS=(com.slogmetaraw.pkg com.sonymeta.pkg)

exists() { [[ -e "$1" || -L "$1" ]]; }
ask() {   # ask "question" -> 0 on s/S
  [[ "$YES" == 1 ]] && return 0
  local a
  read -r -p "$1 [s/N] " a
  [[ "$a" == "s" || "$a" == "S" ]]
}
finish() {
  [[ -t 0 && "$YES" != 1 ]] && read -r -p "Premi Invio per chiudere questa finestra. " _
  exit "$1"
}

echo "Disinstallazione di S-Log MetaRaw (tutte le versioni installate su questo Mac)"
echo
found_sys=() found_usr=() found_rec=()
for p in "${SYSTEM[@]}"; do exists "$p" && found_sys+=("$p"); done
for p in "${USERS[@]}"; do exists "$p" && found_usr+=("$p"); done
if [[ -z "$ROOT" ]]; then
  for r in "${RECEIPTS[@]}"; do pkgutil --pkg-info "$r" >/dev/null 2>&1 && found_rec+=("$r"); done
fi
if (( ${#found_sys[@]} + ${#found_usr[@]} + ${#found_rec[@]} == 0 )); then
  echo "Non c'è niente da rimuovere: S-Log MetaRaw non risulta installato."
  exists "$CSV" && echo "I CSV esportati restano in $CSV."
  finish 0
fi
echo "Verrà rimosso:"
for p in "${found_sys[@]}" "${found_usr[@]}"; do
  if [[ -L "$p" ]]; then echo "  $p  (collegamento: la cartella a cui punta resta)"; else echo "  $p"; fi
done
for r in "${found_rec[@]}"; do echo "  ricevuta dell'installer $r"; done
exists "$CSV" && echo "CSV esportati in $CSV: restano, a meno che tu non chieda di cancellarli."
echo
if [[ "$DRY" == 1 ]]; then
  echo "(Prova: non è stato rimosso niente.)"
  finish 0
fi

ask "Continuare?" || { echo "Annullato: non è stato rimosso niente."; finish 0; }
delete_csv=0
if exists "$CSV"; then
  if [[ "$YES" == 1 ]]; then
    [[ "${SLOGMETARAW_DELETE_CSV:-0}" == 1 ]] && delete_csv=1
  elif ask "Cancellare anche i CSV esportati in $CSV?"; then
    delete_csv=1
  fi
fi

if [[ "${SLOGMETARAW_IGNORE_RESOLVE:-0}" != 1 ]]; then
  while pgrep -x "Resolve" >/dev/null 2>&1; do
    echo "DaVinci Resolve è aperto: chiudilo, poi premi Invio (oppure scrivi 'a' per annullare)."
    read -r a
    [[ "$a" == "a" || "$a" == "A" ]] && { echo "Annullato: non è stato rimosso niente."; finish 0; }
  done
fi

if [[ -n "$SUDO" ]] && (( ${#found_sys[@]} + ${#found_rec[@]} > 0 )); then
  echo "Serve la password di amministratore per le parti di sistema."
  $SUDO -v || { echo "Password non accettata: non è stato rimosso niente."; finish 1; }
fi

# no trailing slash anywhere: on a developer install's symlink rm removes the link, never the working copy
for p in "${found_sys[@]}"; do $SUDO rm -rf -- "$p"; done
for p in "${found_usr[@]}"; do rm -rf -- "$p" 2>/dev/null || $SUDO rm -rf -- "$p"; done
[[ "$delete_csv" == 1 ]] && rm -rf -- "$CSV"
for r in "${found_rec[@]}"; do $SUDO pkgutil --forget "$r" >/dev/null 2>&1; done

left=()
for p in "${found_sys[@]}" "${found_usr[@]}"; do exists "$p" && left+=("$p"); done
[[ "$delete_csv" == 1 ]] && exists "$CSV" && left+=("$CSV")
for r in "${found_rec[@]}"; do pkgutil --pkg-info "$r" >/dev/null 2>&1 && left+=("ricevuta $r"); done
echo
if (( ${#left[@]} > 0 )); then
  echo "Non sono riuscito a rimuovere:"
  for p in "${left[@]}"; do echo "  $p"; done
  finish 1
fi
echo "S-Log MetaRaw è stato rimosso del tutto."
[[ "$delete_csv" == 0 ]] && exists "$CSV" && echo "I CSV esportati restano in $CSV."
echo "I metadata già scritti nei progetti di Resolve (campi, keyword, Data Level) fanno parte dei progetti e restano."
echo "Al prossimo avvio Resolve ricostruisce la lista dei plugin. Ora puoi fare un'installazione pulita."
finish 0
