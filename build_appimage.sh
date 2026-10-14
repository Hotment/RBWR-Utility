#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

mkdir -p publish/releases
APPDIR="publish/AppDir"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/lib"

cp -r publish/linux-x64-standalone/* "${APPDIR}/usr/bin/"
chmod +x "${APPDIR}/usr/bin/RbwrOverlay"

cat << 'EOF' > "${APPDIR}/rbwr-overlay.desktop"
[Desktop Entry]
Name=RBWR APRM Calculator
Comment=Realistic Boiling Water Reactor Transparent APRM & Thermal Calculator
Exec=RbwrOverlay
Icon=icon
Terminal=false
Type=Application
Categories=Utility;Game;
EOF

if [ -f "icon.png" ]; then
  cp icon.png "${APPDIR}/icon.png"
  cp icon.png "${APPDIR}/rbwr-overlay.png"
fi

cat << 'EOF' > "${APPDIR}/AppRun"
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${HERE}/usr/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/RbwrOverlay" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

cd publish
if [ ! -f "appimagetool" ]; then
  wget -q -O appimagetool https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x appimagetool
fi

./appimagetool --appimage-extract >/dev/null 2>&1
ARCH=x86_64 ./squashfs-root/AppRun AppDir releases/RBWR_APRM_Calculator_linux-x64.AppImage
rm -rf squashfs-root AppDir
chmod +x releases/RBWR_APRM_Calculator_linux-x64.AppImage
echo "AppImage created successfully at publish/releases/RBWR_APRM_Calculator_linux-x64.AppImage"