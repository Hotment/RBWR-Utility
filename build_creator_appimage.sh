#!/usr/bin/env bash
# Packages the RBWR Theme Creator Linux x64 standalone build as an AppImage.
# Run build_creator.bat linux-standalone (or appimage) first; usage: build_creator_appimage.sh [version]
set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

SRC_DIR="publish/creator/linux-x64-standalone"
BIN_NAME="RbwrThemeCreator"
OUT_FILE="releases/RBWR_Theme_Creator_linux-x64.AppImage"

if [ ! -f "${SRC_DIR}/${BIN_NAME}" ]; then
  echo "Missing ${SRC_DIR}/${BIN_NAME}. Run: build_creator.bat linux-standalone" >&2
  exit 1
fi

APP_VER="${1:-}"
if [ -z "${APP_VER}" ]; then
  APP_VER=$(grep -oP '<Version>\K[^<]+' RbwrThemeCreator/RbwrThemeCreator.csproj 2>/dev/null || echo "1.0.0")
fi

mkdir -p publish/releases
APPDIR="publish/CreatorAppDir"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin" "${APPDIR}/usr/lib"

cp -r "${SRC_DIR}"/* "${APPDIR}/usr/bin/"
chmod +x "${APPDIR}/usr/bin/${BIN_NAME}"
rm -f "${APPDIR}/usr/bin"/*.pdb "${APPDIR}/usr/bin"/*.dbg

cat << EOF > "${APPDIR}/rbwr-theme-creator.desktop"
[Desktop Entry]
Version=1.0
Name=RBWR Theme Creator
GenericName=Overlay Theme Editor
Comment=Visual theme editor for the RBWR APRM Calculator overlay
Exec=${BIN_NAME}
Icon=icon
Terminal=false
Type=Application
Categories=Utility;Graphics;
X-AppImage-Version=${APP_VER}
EOF

ICON="RbwrThemeCreator/Assets/icon.png"
if [ -f "${ICON}" ]; then
  cp "${ICON}" "${APPDIR}/icon.png"
  cp "${ICON}" "${APPDIR}/rbwr-theme-creator.png"
fi

cat << EOF > "${APPDIR}/AppRun"
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\${0}")")"
export LD_LIBRARY_PATH="\${HERE}/usr/bin:\${HERE}/usr/lib:\${LD_LIBRARY_PATH}"
exec "\${HERE}/usr/bin/${BIN_NAME}" "\$@"
EOF
chmod +x "${APPDIR}/AppRun"

cd publish
if [ ! -f "appimagetool" ]; then
  wget -q -O appimagetool https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x appimagetool
fi

./appimagetool --appimage-extract >/dev/null 2>&1
ARCH=x86_64 ./squashfs-root/AppRun CreatorAppDir "${OUT_FILE}"
rm -rf squashfs-root CreatorAppDir
chmod +x "${OUT_FILE}"
echo "AppImage created successfully at publish/${OUT_FILE}"
