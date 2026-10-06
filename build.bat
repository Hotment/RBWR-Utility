@echo off
setlocal enabledelayedexpansion
title RBWR Overlay Multi-Platform Builder

REM Ensure execution from the repository root directory
cd /d "%~dp0"

echo ==================================================
echo       RBWR AVALONIA OVERLAY BUILD SYSTEM (.NET 8)
echo ==================================================
echo.

REM Verify .NET SDK availability
where dotnet >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] .NET SDK is not installed or not found in system PATH.
    echo Please install the .NET 8 SDK from: https://dotnet.microsoft.com/download
    echo.
    if "%~1"=="" pause
    exit /b 1
)

for /f "tokens=*" %%v in ('dotnet --version') do set "DOTNET_VERSION=%%v"
echo [INFO] Detected .NET SDK Version: %DOTNET_VERSION%

set "PROJECT_PATH=RbwrOverlay\RbwrOverlay.UI\RbwrOverlay.UI.csproj"
if not exist "%PROJECT_PATH%" (
    echo [ERROR] Project file not found: %PROJECT_PATH%
    if "%~1"=="" pause
    exit /b 1
)

if not exist "publish" mkdir "publish"
if not exist "publish\releases" mkdir "publish\releases"

set "TARGET=%~1"
if /i "%TARGET%"=="all" goto build_all
if /i "%TARGET%"=="win-standalone" goto build_win_standalone_only
if /i "%TARGET%"=="win-arm64" goto build_win_arm64_only
if /i "%TARGET%"=="windows" goto build_windows_only
if /i "%TARGET%"=="linux-standalone" goto build_linux_standalone_only
if /i "%TARGET%"=="linux-arm64" goto build_linux_arm64_only
if /i "%TARGET%"=="linux" goto build_linux_only
if /i "%TARGET%"=="mac-arm64" goto build_mac_arm64_only
if /i "%TARGET%"=="mac-x64" goto build_mac_x64_only
if /i "%TARGET%"=="clean" goto do_clean
if /i "%TARGET%"=="help" goto show_help

if not "%TARGET%"=="" (
    echo [ERROR] Unrecognized target argument: %TARGET%
    goto show_help
)

:menu
echo.
echo Select build target:
echo.
echo   [1] Build All Releases: Windows (x64+ARM64), Linux (x64+ARM64), macOS (ARM64+Intel) [Default]
echo   [2] Windows x64 Standalone - Single-File .exe (Shareable - Double-click to run)
echo   [3] Windows ARM64 Standalone - Single-File .exe (Snapdragon X / Surface Pro)
echo   [4] Windows x64 Framework-Dependent (Directory with DLLs)
echo   [5] Linux x64 Standalone (Terminal ./RbwrOverlay + Double-click run.sh + .desktop)
echo   [6] Linux ARM64 Standalone (Raspberry Pi 4/5 / Linux ARM64)
echo   [7] macOS Apple Silicon (ARM64) Standalone (Double-click .app + Terminal ./RbwrOverlay)
echo   [8] macOS Intel (x64) Standalone (Double-click .app + Terminal ./RbwrOverlay)
echo   [9] Clean Publish Directory
echo   [0] Exit
echo.
set /p "CHOICE=Enter choice [1-9, 0 to exit] (Default: 1): "
if "%CHOICE%"=="" set "CHOICE=1"

if "%CHOICE%"=="1" goto build_all
if "%CHOICE%"=="2" goto build_win_standalone_only
if "%CHOICE%"=="3" goto build_win_arm64_only
if "%CHOICE%"=="4" goto build_windows_only
if "%CHOICE%"=="5" goto build_linux_standalone_only
if "%CHOICE%"=="6" goto build_linux_arm64_only
if "%CHOICE%"=="7" goto build_mac_arm64_only
if "%CHOICE%"=="8" goto build_mac_x64_only
if "%CHOICE%"=="9" goto do_clean
if "%CHOICE%"=="0" exit /b 0

echo [WARN] Invalid option selected. Please select a valid number.
goto menu

REM ============================================================================
REM Individual Build Targets
REM ============================================================================

:build_win_standalone_only
call :do_build_win_standalone
goto build_finish

:build_win_arm64_only
call :do_build_win_arm64
goto build_finish

:build_windows_only
call :do_build_windows
goto build_finish

:build_linux_standalone_only
call :do_build_linux_standalone
goto build_finish

:build_linux_arm64_only
call :do_build_linux_arm64
goto build_finish

:build_linux_only
call :do_build_linux
goto build_finish

:build_mac_arm64_only
call :do_build_mac_arm64
goto build_finish

:build_mac_x64_only
call :do_build_mac_x64
goto build_finish

:build_all
echo.
echo [INFO] Starting comprehensive multi-platform release build pipeline...
call :do_build_win_standalone
call :do_build_win_arm64
call :do_build_windows
call :do_build_linux_standalone
call :do_build_linux_arm64
call :do_build_mac_arm64
call :do_build_mac_x64
goto build_finish

REM ============================================================================
REM Core Build Procedures
REM ============================================================================

:do_build_win_standalone
echo.
echo ==================================================
echo Building: Windows x64 Standalone (Single-File .exe)
echo ==================================================
if not exist "publish\win-x64-standalone" mkdir "publish\win-x64-standalone"

dotnet publish "%PROJECT_PATH%" -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -o "publish\win-x64-standalone"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Windows x64 standalone build failed.
    set "ERR_WIN_STANDALONE=1"
    exit /b 1
)

del /q "publish\win-x64-standalone\*.pdb" >nul 2>&1

if exist "publish\win-x64-standalone\RbwrOverlay.exe" (
    copy /y "publish\win-x64-standalone\RbwrOverlay.exe" "publish\win-x64-standalone\RBWR_APRM_Calculator.exe" >nul
    copy /y "publish\win-x64-standalone\RbwrOverlay.exe" "publish\releases\RBWR_APRM_Calculator_win-x64.exe" >nul
)
if exist "icon.ico" copy /y "icon.ico" "publish\win-x64-standalone\icon.ico" >nul

powershell -NoProfile -Command "Compress-Archive -Path 'publish/win-x64-standalone/*' -DestinationPath 'publish/releases/RBWR_APRM_Calculator_Windows_x64.zip' -Force" >nul 2>&1

echo [OK] Windows x64 Standalone published:
echo      - Executable: publish\releases\RBWR_APRM_Calculator_win-x64.exe (Double-click to run)
echo      - Zip Bundle: publish\releases\RBWR_APRM_Calculator_Windows_x64.zip
exit /b 0

:do_build_win_arm64
echo.
echo ==================================================
echo Building: Windows ARM64 Standalone (Single-File .exe)
echo ==================================================
if not exist "publish\win-arm64-standalone" mkdir "publish\win-arm64-standalone"

dotnet publish "%PROJECT_PATH%" -c Release -r win-arm64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -o "publish\win-arm64-standalone"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Windows ARM64 standalone build failed.
    set "ERR_WIN_ARM64=1"
    exit /b 1
)

del /q "publish\win-arm64-standalone\*.pdb" >nul 2>&1

if exist "publish\win-arm64-standalone\RbwrOverlay.exe" (
    copy /y "publish\win-arm64-standalone\RbwrOverlay.exe" "publish\win-arm64-standalone\RBWR_APRM_Calculator.exe" >nul
    copy /y "publish\win-arm64-standalone\RbwrOverlay.exe" "publish\releases\RBWR_APRM_Calculator_win-arm64.exe" >nul
)
if exist "icon.ico" copy /y "icon.ico" "publish\win-arm64-standalone\icon.ico" >nul

powershell -NoProfile -Command "Compress-Archive -Path 'publish/win-arm64-standalone/*' -DestinationPath 'publish/releases/RBWR_APRM_Calculator_Windows_ARM64.zip' -Force" >nul 2>&1

echo [OK] Windows ARM64 Standalone published:
echo      - Executable: publish\releases\RBWR_APRM_Calculator_win-arm64.exe
echo      - Zip Bundle: publish\releases\RBWR_APRM_Calculator_Windows_ARM64.zip
exit /b 0

:do_build_windows
echo.
echo ==================================================
echo Building: Windows x64 Framework-Dependent
echo ==================================================
if not exist "publish\win-x64" mkdir "publish\win-x64"

dotnet publish "%PROJECT_PATH%" -c Release -r win-x64 --self-contained false -p:PublishSingleFile=true -o "publish\win-x64"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Windows framework-dependent build failed.
    set "ERR_WINDOWS=1"
    exit /b 1
)

del /q "publish\win-x64\*.pdb" >nul 2>&1
if exist "icon.ico" copy /y "icon.ico" "publish\win-x64\icon.ico" >nul

echo [OK] Windows framework-dependent published to: publish\win-x64\
exit /b 0

:do_build_linux_standalone
echo.
echo ==================================================
echo Building: Linux x64 Standalone
echo ==================================================
if not exist "publish\linux-x64-standalone" mkdir "publish\linux-x64-standalone"

dotnet publish "%PROJECT_PATH%" -c Release -r linux-x64 --self-contained true -p:PublishSingleFile=true -o "publish\linux-x64-standalone"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Linux x64 standalone build failed.
    set "ERR_LINUX_STANDALONE=1"
    exit /b 1
)

del /q "publish\linux-x64-standalone\*.pdb" >nul 2>&1

if exist "publish\linux-x64-standalone\RbwrOverlay" (
    copy /y "publish\linux-x64-standalone\RbwrOverlay" "publish\linux-x64-standalone\RBWR_APRM_Calculator" >nul
    copy /y "publish\linux-x64-standalone\RbwrOverlay" "publish\releases\RbwrOverlay_linux-x64" >nul
)
if exist "icon.png" copy /y "icon.png" "publish\linux-x64-standalone\icon.png" >nul

> "publish\linux-x64-standalone\run.sh" echo #^^!/usr/bin/env bash
>> "publish\linux-x64-standalone\run.sh" echo SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" ^&^& pwd)"
>> "publish\linux-x64-standalone\run.sh" echo export LD_LIBRARY_PATH="${SCRIPT_DIR}:${LD_LIBRARY_PATH}"
>> "publish\linux-x64-standalone\run.sh" echo chmod +x "${SCRIPT_DIR}/RbwrOverlay" 2^>/dev/null
>> "publish\linux-x64-standalone\run.sh" echo exec "${SCRIPT_DIR}/RbwrOverlay" "$@"

> "publish\linux-x64-standalone\rbwr-overlay.desktop" echo [Desktop Entry]
>> "publish\linux-x64-standalone\rbwr-overlay.desktop" echo Name=RBWR APRM Calculator
>> "publish\linux-x64-standalone\rbwr-overlay.desktop" echo Comment=Realistic Boiling Water Reactor Transparent APRM & Thermal Calculator
>> "publish\linux-x64-standalone\rbwr-overlay.desktop" echo Exec=sh -c '"$(dirname "%%k")/run.sh"'
>> "publish\linux-x64-standalone\rbwr-overlay.desktop" echo Icon=icon.png
>> "publish\linux-x64-standalone\rbwr-overlay.desktop" echo Terminal=false
>> "publish\linux-x64-standalone\rbwr-overlay.desktop" echo Type=Application
>> "publish\linux-x64-standalone\rbwr-overlay.desktop" echo Categories=Utility;Game;

where tar >nul 2>&1
if %ERRORLEVEL% equ 0 (
    tar -czf "publish\releases\RBWR_APRM_Calculator_Linux_x64.tar.gz" -C "publish" "linux-x64-standalone" >nul 2>&1
)
powershell -NoProfile -Command "Compress-Archive -Path 'publish/linux-x64-standalone/*' -DestinationPath 'publish/releases/RBWR_APRM_Calculator_Linux_x64.zip' -Force" >nul 2>&1

echo [OK] Linux x64 Standalone published:
echo      - Binary: ./RbwrOverlay (or run ./run.sh)
echo      - Desktop Entry: rbwr-overlay.desktop (double-click to run)
echo      - Archives: publish\releases\RBWR_APRM_Calculator_Linux_x64.tar.gz (.zip)
exit /b 0

:do_build_linux_arm64
echo.
echo ==================================================
echo Building: Linux ARM64 Standalone (Raspberry Pi 4/5)
echo ==================================================
if not exist "publish\linux-arm64-standalone" mkdir "publish\linux-arm64-standalone"

dotnet publish "%PROJECT_PATH%" -c Release -r linux-arm64 --self-contained true -p:PublishSingleFile=true -o "publish\linux-arm64-standalone"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Linux ARM64 standalone build failed.
    set "ERR_LINUX_ARM64=1"
    exit /b 1
)

del /q "publish\linux-arm64-standalone\*.pdb" >nul 2>&1

if exist "publish\linux-arm64-standalone\RbwrOverlay" (
    copy /y "publish\linux-arm64-standalone\RbwrOverlay" "publish\linux-arm64-standalone\RBWR_APRM_Calculator" >nul
)
if exist "icon.png" copy /y "icon.png" "publish\linux-arm64-standalone\icon.png" >nul

> "publish\linux-arm64-standalone\run.sh" echo #^^!/usr/bin/env bash
>> "publish\linux-arm64-standalone\run.sh" echo SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" ^&^& pwd)"
>> "publish\linux-arm64-standalone\run.sh" echo export LD_LIBRARY_PATH="${SCRIPT_DIR}:${LD_LIBRARY_PATH}"
>> "publish\linux-arm64-standalone\run.sh" echo chmod +x "${SCRIPT_DIR}/RbwrOverlay" 2^>/dev/null
>> "publish\linux-arm64-standalone\run.sh" echo exec "${SCRIPT_DIR}/RbwrOverlay" "$@"

> "publish\linux-arm64-standalone\rbwr-overlay.desktop" echo [Desktop Entry]
>> "publish\linux-arm64-standalone\rbwr-overlay.desktop" echo Name=RBWR APRM Calculator
>> "publish\linux-arm64-standalone\rbwr-overlay.desktop" echo Comment=Realistic Boiling Water Reactor Transparent APRM & Thermal Calculator
>> "publish\linux-arm64-standalone\rbwr-overlay.desktop" echo Exec=sh -c '"$(dirname "%%k")/run.sh"'
>> "publish\linux-arm64-standalone\rbwr-overlay.desktop" echo Icon=icon.png
>> "publish\linux-arm64-standalone\rbwr-overlay.desktop" echo Terminal=false
>> "publish\linux-arm64-standalone\rbwr-overlay.desktop" echo Type=Application
>> "publish\linux-arm64-standalone\rbwr-overlay.desktop" echo Categories=Utility;Game;

where tar >nul 2>&1
if %ERRORLEVEL% equ 0 (
    tar -czf "publish\releases\RBWR_APRM_Calculator_Linux_ARM64.tar.gz" -C "publish" "linux-arm64-standalone" >nul 2>&1
)
powershell -NoProfile -Command "Compress-Archive -Path 'publish/linux-arm64-standalone/*' -DestinationPath 'publish/releases/RBWR_APRM_Calculator_Linux_ARM64.zip' -Force" >nul 2>&1

echo [OK] Linux ARM64 Standalone published:
echo      - Archives: publish\releases\RBWR_APRM_Calculator_Linux_ARM64.tar.gz (.zip)
exit /b 0

:do_build_linux
echo.
echo ==================================================
echo Building: Linux x64 Framework-Dependent
echo ==================================================
if not exist "publish\linux-x64" mkdir "publish\linux-x64"

dotnet publish "%PROJECT_PATH%" -c Release -r linux-x64 --self-contained false -p:PublishSingleFile=true -o "publish\linux-x64"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Linux framework-dependent build failed.
    set "ERR_LINUX=1"
    exit /b 1
)

del /q "publish\linux-x64\*.pdb" >nul 2>&1
if exist "icon.png" copy /y "icon.png" "publish\linux-x64\icon.png" >nul

echo [OK] Linux framework-dependent published to: publish\linux-x64\
exit /b 0

:do_build_mac_arm64
echo.
echo ==================================================
echo Building: macOS Apple Silicon (ARM64) Standalone
echo ==================================================
set "MAC_DIR=publish\mac-arm64-standalone"
set "APP_DIR=!MAC_DIR!\RBWR APRM Calculator.app"
if exist "!MAC_DIR!" rmdir /s /q "!MAC_DIR!" >nul 2>&1
mkdir "!APP_DIR!\Contents\MacOS" >nul 2>&1
mkdir "!APP_DIR!\Contents\Resources" >nul 2>&1

dotnet publish "%PROJECT_PATH%" -c Release -r osx-arm64 --self-contained true -p:PublishSingleFile=true -o "publish\osx-arm64-tmp"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] macOS ARM64 build failed.
    set "ERR_MAC_ARM64=1"
    exit /b 1
)

del /q "publish\osx-arm64-tmp\*.pdb" >nul 2>&1
xcopy /e /y /q "publish\osx-arm64-tmp\*" "!APP_DIR!\Contents\MacOS\" >nul
rmdir /s /q "publish\osx-arm64-tmp" >nul 2>&1

if exist "!APP_DIR!\Contents\MacOS\RbwrOverlay" (
    copy /y "!APP_DIR!\Contents\MacOS\RbwrOverlay" "!MAC_DIR!\RbwrOverlay" >nul
)
if exist "icon.png" copy /y "icon.png" "!APP_DIR!\Contents\Resources\icon.png" >nul

> "!APP_DIR!\Contents\Info.plist" echo ^<?xml version="1.0" encoding="UTF-8"?^>
>> "!APP_DIR!\Contents\Info.plist" echo ^<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"^>
>> "!APP_DIR!\Contents\Info.plist" echo ^<plist version="1.0"^>
>> "!APP_DIR!\Contents\Info.plist" echo ^<dict^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleName^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>RBWR APRM Calculator^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleDisplayName^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>RBWR APRM Calculator^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleIdentifier^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>com.hotment.rbwroverlay^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleVersion^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>1.0.0^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundlePackageType^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>APPL^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleExecutable^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>RbwrOverlay^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>NSHighResolutionCapable^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<true/^>
>> "!APP_DIR!\Contents\Info.plist" echo ^</dict^>
>> "!APP_DIR!\Contents\Info.plist" echo ^</plist^>

> "!MAC_DIR!\run.command" echo #^^!/usr/bin/env bash
>> "!MAC_DIR!\run.command" echo DIR="$(cd "$(dirname "$0")" ^&^& pwd)"
>> "!MAC_DIR!\run.command" echo chmod +x "${DIR}/RBWR APRM Calculator.app/Contents/MacOS/RbwrOverlay" 2^>/dev/null
>> "!MAC_DIR!\run.command" echo exec "${DIR}/RBWR APRM Calculator.app/Contents/MacOS/RbwrOverlay" "$@"

powershell -NoProfile -Command "Compress-Archive -Path '!MAC_DIR!/*' -DestinationPath 'publish/releases/RBWR_APRM_Calculator_macOS_AppleSilicon.zip' -Force" >nul 2>&1

echo [OK] macOS Apple Silicon (ARM64) published:
echo      - Double-click App: 'RBWR APRM Calculator.app'
echo      - Terminal binary: ./RbwrOverlay (or run.command)
echo      - Zip Package: publish\releases\RBWR_APRM_Calculator_macOS_AppleSilicon.zip
exit /b 0

:do_build_mac_x64
echo.
echo ==================================================
echo Building: macOS Intel (x64) Standalone
echo ==================================================
set "MAC_DIR=publish\mac-x64-standalone"
set "APP_DIR=!MAC_DIR!\RBWR APRM Calculator.app"
if exist "!MAC_DIR!" rmdir /s /q "!MAC_DIR!" >nul 2>&1
mkdir "!APP_DIR!\Contents\MacOS" >nul 2>&1
mkdir "!APP_DIR!\Contents\Resources" >nul 2>&1

dotnet publish "%PROJECT_PATH%" -c Release -r osx-x64 --self-contained true -p:PublishSingleFile=true -o "publish\osx-x64-tmp"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] macOS Intel x64 build failed.
    set "ERR_MAC_X64=1"
    exit /b 1
)

del /q "publish\osx-x64-tmp\*.pdb" >nul 2>&1
xcopy /e /y /q "publish\osx-x64-tmp\*" "!APP_DIR!\Contents\MacOS\" >nul
rmdir /s /q "publish\osx-x64-tmp" >nul 2>&1

if exist "!APP_DIR!\Contents\MacOS\RbwrOverlay" (
    copy /y "!APP_DIR!\Contents\MacOS\RbwrOverlay" "!MAC_DIR!\RbwrOverlay" >nul
)
if exist "icon.png" copy /y "icon.png" "!APP_DIR!\Contents\Resources\icon.png" >nul

> "!APP_DIR!\Contents\Info.plist" echo ^<?xml version="1.0" encoding="UTF-8"?^>
>> "!APP_DIR!\Contents\Info.plist" echo ^<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"^>
>> "!APP_DIR!\Contents\Info.plist" echo ^<plist version="1.0"^>
>> "!APP_DIR!\Contents\Info.plist" echo ^<dict^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleName^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>RBWR APRM Calculator^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleDisplayName^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>RBWR APRM Calculator^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleIdentifier^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>com.hotment.rbwroverlay^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleVersion^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>1.0.0^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundlePackageType^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>APPL^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleExecutable^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>RbwrOverlay^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>NSHighResolutionCapable^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<true/^>
>> "!APP_DIR!\Contents\Info.plist" echo ^</dict^>
>> "!APP_DIR!\Contents\Info.plist" echo ^</plist^>

> "!MAC_DIR!\run.command" echo #^^!/usr/bin/env bash
>> "!MAC_DIR!\run.command" echo DIR="$(cd "$(dirname "$0")" ^&^& pwd)"
>> "!MAC_DIR!\run.command" echo chmod +x "${DIR}/RBWR APRM Calculator.app/Contents/MacOS/RbwrOverlay" 2^>/dev/null
>> "!MAC_DIR!\run.command" echo exec "${DIR}/RBWR APRM Calculator.app/Contents/MacOS/RbwrOverlay" "$@"

powershell -NoProfile -Command "Compress-Archive -Path '!MAC_DIR!/*' -DestinationPath 'publish/releases/RBWR_APRM_Calculator_macOS_Intel.zip' -Force" >nul 2>&1

echo [OK] macOS Intel (x64) published:
echo      - Double-click App: 'RBWR APRM Calculator.app'
echo      - Terminal binary: ./RbwrOverlay (or run.command)
echo      - Zip Package: publish\releases\RBWR_APRM_Calculator_macOS_Intel.zip
exit /b 0

REM ============================================================================
REM Clean Procedure
REM ============================================================================

:do_clean
echo.
echo [CLEAN] Cleaning publish directory...
if exist "publish" (
    rmdir /s /q "publish"
    echo [OK] publish directory removed.
) else (
    echo [INFO] publish directory does not exist. Nothing to clean.
)
if "%~1"=="" pause
exit /b 0

REM ============================================================================
REM Build Completion Summary
REM ============================================================================

:build_finish
echo.
echo ==================================================
echo                  BUILD SUMMARY
echo ==================================================

powershell -NoProfile -Command "$releases = Get-ChildItem -Path 'publish/releases' -ErrorAction SilentlyContinue; if ($releases) { Write-Host '--- Release Packages Ready For Distribution ---' -ForegroundColor Cyan; $releases | Select-Object Name, @{Name='Size (MB)';Expression={[math]::Round($_.Length / 1MB, 2)}} | Format-Table -AutoSize } else { Write-Host 'No packaged release files found in publish/releases.' }"

set "HAS_FAILURES=0"
if defined ERR_WIN_STANDALONE (
    echo [!] Windows x64 standalone build encountered errors.
    set "HAS_FAILURES=1"
)
if defined ERR_WIN_ARM64 (
    echo [!] Windows ARM64 standalone build encountered errors.
    set "HAS_FAILURES=1"
)
if defined ERR_WINDOWS (
    echo [!] Windows framework-dependent build encountered errors.
    set "HAS_FAILURES=1"
)
if defined ERR_LINUX_STANDALONE (
    echo [!] Linux x64 standalone build encountered errors.
    set "HAS_FAILURES=1"
)
if defined ERR_LINUX_ARM64 (
    echo [!] Linux ARM64 standalone build encountered errors.
    set "HAS_FAILURES=1"
)
if defined ERR_MAC_ARM64 (
    echo [!] macOS ARM64 build encountered errors.
    set "HAS_FAILURES=1"
)
if defined ERR_MAC_X64 (
    echo [!] macOS Intel build encountered errors.
    set "HAS_FAILURES=1"
)

if "%HAS_FAILURES%"=="0" (
    echo.
    echo ALL REQUESTED BUILDS COMPLETED SUCCESSFULLY.
)

echo ==================================================
echo.
if "%~1"=="" pause
exit /b %HAS_FAILURES%

REM ============================================================================
REM Usage & Help
REM ============================================================================

:show_help
echo.
echo Usage:
echo   build.bat [target]
echo.
echo Available Targets:
echo   all                 Build all release targets (Windows, Linux, macOS)
echo   win-standalone      Build Windows x64 standalone single-file (.exe - double-click to run)
echo   win-arm64           Build Windows ARM64 standalone single-file (Snapdragon / Surface Pro)
echo   windows             Build Windows framework-dependent (publish\win-x64)
echo   linux-standalone    Build Linux x64 standalone (terminal ./RbwrOverlay, run.sh, .desktop)
echo   linux-arm64         Build Linux ARM64 standalone (Raspberry Pi 4/5)
echo   linux               Build Linux framework-dependent (publish\linux-x64)
echo   mac-arm64           Build macOS Apple Silicon ARM64 standalone (.app + ./RbwrOverlay)
echo   mac-x64             Build macOS Intel x64 standalone (.app + ./RbwrOverlay)
echo   clean               Delete the publish\ directory
echo   help                Display this help screen
echo.
echo If run without arguments, an interactive menu is displayed.
exit /b 0