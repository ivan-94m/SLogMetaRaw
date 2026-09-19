#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Builds dist/SLogMetaRaw-<version>.dmg with the installer (.pkg), the one-page guide and the uninstaller.
#   ./packaging/build_installer.sh
set -euo pipefail
export COPYFILE_DISABLE=1   # no AppleDouble ._ files in the package
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG_DIR="$ROOT/packaging"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import slogmetaraw; print(slogmetaraw.__version__)")"
BUILD="$ROOT/build/installer"
DIST="$ROOT/dist"
rm -rf "$BUILD" && mkdir -p "$BUILD/root" "$BUILD/resources" "$BUILD/dmg" "$DIST"

echo "1/6 plugin"
make -C "$ROOT/ofx/SLogMetaRaw" >/dev/null

echo "2/6 icone e guida"
swift "$ROOT/tools/make_icons.swift" "$ROOT/assets" >/dev/null
# .icns for the installer package and the disk image
ICONSET="$BUILD/SLogMetaRaw.iconset"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$ROOT/assets/icon_1024.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$ROOT/assets/icon_1024.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ROOT/assets/SLogMetaRaw.icns"
cp "$ROOT/assets/effect_256.png" "$ROOT/ofx/SLogMetaRaw/com.slogmetaraw.SLogMetaRaw.png"
make -C "$ROOT/ofx/SLogMetaRaw" >/dev/null
cp "$ROOT/assets/icon_1024.png" "$PKG_DIR/guide/icon.png"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
    --print-to-pdf="$BUILD/dmg/Guida S-Log MetaRaw (italiano).pdf" "file://$PKG_DIR/guide/guida.html" 2>/dev/null
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
    --print-to-pdf="$BUILD/dmg/S-Log MetaRaw Guide (english).pdf" "file://$PKG_DIR/guide/guide-en.html" 2>/dev/null
# each guide must stay a single page
for g in "$BUILD/dmg/Guida S-Log MetaRaw (italiano).pdf" "$BUILD/dmg/S-Log MetaRaw Guide (english).pdf"; do
  python3 - "$g" <<'EOF'
import sys
d = open(sys.argv[1], 'rb').read()
n = d.count(b'/Type /Page') - d.count(b'/Type /Pages')
if n != 1:
    sys.exit('%s: %d pagine invece di 1' % (sys.argv[1], n))
EOF
done

echo "3/6 contenuto del pacchetto"
R="$BUILD/root"
mkdir -p "$R/Library/OFX/Plugins" "$R/Library/Application Support/SLogMetaRaw/lib" \
         "$R/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
cp -R "$ROOT/ofx/SLogMetaRaw/SLogMetaRaw.ofx.bundle" "$R/Library/OFX/Plugins/"
rsync -a --exclude "__pycache__" "$ROOT/slogmetaraw" "$R/Library/Application Support/SLogMetaRaw/lib/"
sed "s|__LIB_DIR__|/Library/Application Support/SLogMetaRaw/lib|" "$ROOT/resolve_script/SLogMetaRaw.py" \
    > "$R/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py"
find "$R" -name ".DS_Store" -delete
xattr -rc "$R"

echo "4/6 pacchetto"
pkgbuild --root "$R" --install-location / --identifier com.slogmetaraw.pkg --version "$VERSION" \
         --scripts "$PKG_DIR/scripts" "$BUILD/SLogMetaRaw-component.pkg" > "$BUILD/pkgbuild.log" 2>&1
cp "$PKG_DIR/resources/"* "$BUILD/resources/"
sips -z 190 190 "$ROOT/assets/icon_1024.png" --out "$BUILD/resources/background.png" >/dev/null
productbuild --distribution "$PKG_DIR/distribution.xml" --resources "$BUILD/resources" \
             --package-path "$BUILD" "$BUILD/dmg/Installa S-Log MetaRaw.pkg" > "$BUILD/productbuild.log" 2>&1
swift "$ROOT/tools/set_icon.swift" "$ROOT/assets/SLogMetaRaw.icns" "$BUILD/dmg/Installa S-Log MetaRaw.pkg"

echo "5/6 disinstallatore"
cp "$PKG_DIR/Disinstalla S-Log MetaRaw.command" "$BUILD/dmg/"
cp "$ROOT/assets/SLogMetaRaw.icns" "$BUILD/dmg/.VolumeIcon.icns"
xattr -c "$BUILD/dmg/Guida S-Log MetaRaw (italiano).pdf" "$BUILD/dmg/S-Log MetaRaw Guide (english).pdf" \
         "$BUILD/dmg/Disinstalla S-Log MetaRaw.command" "$BUILD/dmg/.VolumeIcon.icns"

echo "6/6 disco"
DMG="$DIST/SLogMetaRaw-$VERSION.dmg"
rm -f "$DMG" "$BUILD/rw.dmg"
hdiutil create -quiet -volname "S-Log MetaRaw $VERSION" -srcfolder "$BUILD/dmg" -fs HFS+ -format UDRW "$BUILD/rw.dmg"
MNT="$(hdiutil attach -nobrowse -noverify -noautoopen "$BUILD/rw.dmg" | awk -F'\t' '/\/Volumes\//{print $NF}')"
xcrun SetFile -a C "$MNT" 2>/dev/null || true   # show .VolumeIcon.icns as the disk icon
hdiutil detach -quiet "$MNT"
hdiutil convert -quiet "$BUILD/rw.dmg" -format UDZO -o "$DMG"
swift "$ROOT/tools/set_icon.swift" "$ROOT/assets/SLogMetaRaw.icns" "$DMG"
echo "Creato: $DMG"
