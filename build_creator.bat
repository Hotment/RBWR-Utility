@echo off
setlocal enabledelayedexpansion
title RBWR Theme Creator Multi-Platform Builder

REM Ensure execution from the repository root directory
cd /d "%~dp0"

echo ==================================================
echo     RBWR THEME CREATOR BUILD SYSTEM (.NET 8)
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

set "PROJECT_PATH=RbwrThemeCreator\RbwrThemeCreator.csproj"
if not exist "%PROJECT_PATH%" (
    echo [ERROR] Project file not found: %PROJECT_PATH%
    if "%~1"=="" pause
    exit /b 1
)

set "BIN_NAME=RbwrThemeCreator"
set "RELEASE_NAME=RBWR_Theme_Creator"
set "APP_DISPLAY=RBWR Theme Creator"
set "ICON_ICO=RbwrThemeCreator\Assets\icon.ico"
set "ICON_PNG=RbwrThemeCreator\Assets\icon.png"
set "OUT_ROOT=publish\creator"

REM Version comes from MainViewModel.AppVersion (single source of truth)
set "APP_VER=1.0.0"
for /f "tokens=2 delims==" %%A in ('findstr /c:"public const string AppVersion" "RbwrThemeCreator\ViewModels\MainViewModel.cs"') do (
    set "RAW_VER=%%A"
    set "RAW_VER=!RAW_VER:"=!"
    set "RAW_VER=!RAW_VER:;=!"
    set "RAW_VER=!RAW_VER: =!"
    if not "!RAW_VER!"=="" set "APP_VER=!RAW_VER!"
)

for /f "tokens=1 delims=-" %%A in ("!APP_VER!") do set "SEM_BASE=%%A"
for /f "tokens=1,2,3,4 delims=." %%A in ("!SEM_BASE!") do (
    set "P1=%%A"
    set "P2=%%B"
    set "P3=%%C"
    set "P4=%%D"
)
if "!P1!"=="" set "P1=1"
if "!P2!"=="" set "P2=0"
if "!P3!"=="" set "P3=0"
if "!P4!"=="" set "P4=0"
set "NUMERIC_VER=!P1!.!P2!.!P3!.!P4!"

echo [INFO] Detected Theme Creator Version: !APP_VER! (PE File Version: !NUMERIC_VER!)
echo [INFO] Executable Details: RBWR Theme Creator by Hotment

set BUILD_METADATA=-p:Version="!APP_VER!" -p:InformationalVersion="!APP_VER!" -p:AssemblyVersion="!NUMERIC_VER!" -p:FileVersion="!NUMERIC_VER!" -p:Product="RBWR Theme Creator" -p:AssemblyTitle="RBWR Theme Creator" -p:Title="RBWR Theme Creator" -p:Description="Visual theme editor for the RBWR APRM Calculator overlay" -p:Company="Hotment" -p:Authors="Hotment" -p:Copyright="Copyright (C) 2026 Hotment" -p:IncludeSourceRevisionInInformationalVersion=false -p:DebugType=none -p:DebugSymbols=false
set SINGLE_FILE=-p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true

if not exist "publish" mkdir "publish"
if not exist "publish\releases" mkdir "publish\releases"
if not exist "%OUT_ROOT%" mkdir "%OUT_ROOT%"

set "TARGET=%~1"
if /i "%TARGET%"=="all" goto build_all
if /i "%TARGET%"=="win-standalone" goto build_win_standalone_only
if /i "%TARGET%"=="win-arm64" goto build_win_arm64_only
if /i "%TARGET%"=="windows" goto build_windows_only
if /i "%TARGET%"=="linux-standalone" goto build_linux_standalone_only
if /i "%TARGET%"=="linux-arm64" goto build_linux_arm64_only
if /i "%TARGET%"=="appimage" goto build_appimage_only
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
echo   [1] Build All Releases: Windows (x64+ARM64), Linux (x64+ARM64+AppImage), macOS (ARM64+Intel) [Default]
echo   [2] Windows x64 Standalone - Single-File .exe (Shareable - Double-click to run)
echo   [3] Windows ARM64 Standalone - Single-File .exe (Snapdragon X / Surface Pro)
echo   [4] Windows x64 Framework-Dependent (Directory with DLLs)
echo   [5] Linux x64 Standalone (Terminal ./RbwrThemeCreator + Double-click run.sh + .desktop)
echo   [6] Linux ARM64 Standalone (Raspberry Pi 4/5 / Linux ARM64)
echo   [7] Linux x64 AppImage (.AppImage Package via WSL or Linux)
echo   [8] macOS Apple Silicon (ARM64) Standalone (Double-click .app + Terminal ./RbwrThemeCreator)
echo   [9] macOS Intel (x64) Standalone (Double-click .app + Terminal ./RbwrThemeCreator)
echo  [10] Clean Theme Creator Publish Output
echo   [0] Exit
echo.
set /p "CHOICE=Enter choice [1-10, 0 to exit] (Default: 1): "
if "%CHOICE%"=="" set "CHOICE=1"

if "%CHOICE%"=="1" goto build_all
if "%CHOICE%"=="2" goto build_win_standalone_only
if "%CHOICE%"=="3" goto build_win_arm64_only
if "%CHOICE%"=="4" goto build_windows_only
if "%CHOICE%"=="5" goto build_linux_standalone_only
if "%CHOICE%"=="6" goto build_linux_arm64_only
if "%CHOICE%"=="7" goto build_appimage_only
if "%CHOICE%"=="8" goto build_mac_arm64_only
if "%CHOICE%"=="9" goto build_mac_x64_only
if "%CHOICE%"=="10" goto do_clean
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

:build_appimage_only
call :do_build_appimage
goto build_finish

:build_mac_arm64_only
call :do_build_mac_arm64
goto build_finish

:build_mac_x64_only
call :do_build_mac_x64
goto build_finish

:build_all
echo.
echo [INFO] Starting comprehensive multi-platform Theme Creator release build pipeline...
call :do_build_win_standalone
call :do_build_win_arm64
call :do_build_windows
call :do_build_linux_standalone
call :do_build_linux_arm64
call :do_build_appimage
call :do_build_mac_arm64
call :do_build_mac_x64
goto build_finish

REM ============================================================================
REM Core Build Procedures
REM ============================================================================

:do_build_win_standalone
call :build_windows_single "win-x64" "win-x64-standalone" "Windows_x64" "ERR_WIN_STANDALONE" "Windows x64"
exit /b %ERRORLEVEL%

:do_build_win_arm64
call :build_windows_single "win-arm64" "win-arm64-standalone" "Windows_ARM64" "ERR_WIN_ARM64" "Windows ARM64"
exit /b %ERRORLEVEL%

REM %1=RID %2=output folder %3=release suffix %4=error flag %5=label
:build_windows_single
echo.
echo ==================================================
echo Building: Theme Creator %~5 Standalone (Single-File .exe)
echo ==================================================
set "OUT=%OUT_ROOT%\%~2"
if not exist "!OUT!" mkdir "!OUT!"

dotnet publish "%PROJECT_PATH%" -c Release -r %~1 --self-contained true %SINGLE_FILE% %BUILD_METADATA% -o "!OUT!"

if !ERRORLEVEL! neq 0 (
    echo [ERROR] Theme Creator %~5 standalone build failed.
    set "%~4=1"
    exit /b 1
)

del /q "!OUT!\*.pdb" >nul 2>&1

if exist "!OUT!\%BIN_NAME%.exe" (
    copy /y "!OUT!\%BIN_NAME%.exe" "!OUT!\%RELEASE_NAME%.exe" >nul
    copy /y "!OUT!\%BIN_NAME%.exe" "publish\releases\%RELEASE_NAME%_%~1.exe" >nul
)
if exist "%ICON_ICO%" copy /y "%ICON_ICO%" "!OUT!\icon.ico" >nul

powershell -NoProfile -Command "Compress-Archive -Path '!OUT!/*' -DestinationPath 'publish/releases/%RELEASE_NAME%_%~3.zip' -CompressionLevel Optimal -Force" >nul 2>&1

echo [OK] Theme Creator %~5 Standalone published:
echo      - Executable: publish\releases\%RELEASE_NAME%_%~1.exe (Double-click to run)
echo      - Zip Bundle: publish\releases\%RELEASE_NAME%_%~3.zip
exit /b 0

:do_build_windows
echo.
echo ==================================================
echo Building: Theme Creator Windows x64 Framework-Dependent
echo ==================================================
set "OUT=%OUT_ROOT%\win-x64"
if not exist "!OUT!" mkdir "!OUT!"

dotnet publish "%PROJECT_PATH%" -c Release -r win-x64 --self-contained false -p:PublishSingleFile=true %BUILD_METADATA% -o "!OUT!"

if !ERRORLEVEL! neq 0 (
    echo [ERROR] Theme Creator Windows framework-dependent build failed.
    set "ERR_WINDOWS=1"
    exit /b 1
)

del /q "!OUT!\*.pdb" >nul 2>&1
if exist "%ICON_ICO%" copy /y "%ICON_ICO%" "!OUT!\icon.ico" >nul

echo [OK] Theme Creator Windows framework-dependent published to: !OUT!\
exit /b 0

:do_build_linux_standalone
call :build_linux_single "linux-x64" "linux-x64-standalone" "Linux_x64" "ERR_LINUX_STANDALONE" "Linux x64"
exit /b %ERRORLEVEL%

:do_build_linux_arm64
call :build_linux_single "linux-arm64" "linux-arm64-standalone" "Linux_ARM64" "ERR_LINUX_ARM64" "Linux ARM64"
exit /b %ERRORLEVEL%

REM %1=RID %2=output folder %3=release suffix %4=error flag %5=label
:build_linux_single
echo.
echo ==================================================
echo Building: Theme Creator %~5 Standalone
echo ==================================================
set "OUT=%OUT_ROOT%\%~2"
if not exist "!OUT!" mkdir "!OUT!"

dotnet publish "%PROJECT_PATH%" -c Release -r %~1 --self-contained true %SINGLE_FILE% %BUILD_METADATA% -o "!OUT!"

if !ERRORLEVEL! neq 0 (
    echo [ERROR] Theme Creator %~5 standalone build failed.
    set "%~4=1"
    exit /b 1
)

del /q "!OUT!\*.pdb" >nul 2>&1

if exist "!OUT!\%BIN_NAME%" (
    copy /y "!OUT!\%BIN_NAME%" "!OUT!\%RELEASE_NAME%" >nul
    copy /y "!OUT!\%BIN_NAME%" "publish\releases\%BIN_NAME%_%~1" >nul
)
if exist "%ICON_PNG%" copy /y "%ICON_PNG%" "!OUT!\icon.png" >nul

> "!OUT!\run.sh" echo #^^!/usr/bin/env bash
>> "!OUT!\run.sh" echo SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
>> "!OUT!\run.sh" echo export LD_LIBRARY_PATH="${SCRIPT_DIR}:${LD_LIBRARY_PATH}"
>> "!OUT!\run.sh" echo chmod +x "${SCRIPT_DIR}/%BIN_NAME%" 2^>/dev/null
>> "!OUT!\run.sh" echo exec "${SCRIPT_DIR}/%BIN_NAME%" "$@"

> "!OUT!\rbwr-theme-creator.desktop" echo [Desktop Entry]
>> "!OUT!\rbwr-theme-creator.desktop" echo Version=1.0
>> "!OUT!\rbwr-theme-creator.desktop" echo Name=%APP_DISPLAY%
>> "!OUT!\rbwr-theme-creator.desktop" echo GenericName=Overlay Theme Editor
>> "!OUT!\rbwr-theme-creator.desktop" echo Comment=Visual theme editor for the RBWR APRM Calculator overlay
>> "!OUT!\rbwr-theme-creator.desktop" echo Exec=sh -c '"$(dirname "%%k")/run.sh"'
>> "!OUT!\rbwr-theme-creator.desktop" echo Icon=icon.png
>> "!OUT!\rbwr-theme-creator.desktop" echo Terminal=false
>> "!OUT!\rbwr-theme-creator.desktop" echo Type=Application
>> "!OUT!\rbwr-theme-creator.desktop" echo Categories=Utility;Graphics;
>> "!OUT!\rbwr-theme-creator.desktop" echo X-AppImage-Version=!APP_VER!

where tar >nul 2>&1
if !ERRORLEVEL! equ 0 (
    tar -czf "publish\releases\%RELEASE_NAME%_%~3.tar.gz" -C "%OUT_ROOT%" "%~2" >nul 2>&1
)
powershell -NoProfile -Command "Compress-Archive -Path '!OUT!/*' -DestinationPath 'publish/releases/%RELEASE_NAME%_%~3.zip' -CompressionLevel Optimal -Force" >nul 2>&1

echo [OK] Theme Creator %~5 Standalone published:
echo      - Binary: ./%BIN_NAME% (or run ./run.sh)
echo      - Desktop Entry: rbwr-theme-creator.desktop (double-click to run)
echo      - Archives: publish\releases\%RELEASE_NAME%_%~3.tar.gz (.zip)
exit /b 0

:do_build_linux
echo.
echo ==================================================
echo Building: Theme Creator Linux x64 Framework-Dependent
echo ==================================================
set "OUT=%OUT_ROOT%\linux-x64"
if not exist "!OUT!" mkdir "!OUT!"

dotnet publish "%PROJECT_PATH%" -c Release -r linux-x64 --self-contained false -p:PublishSingleFile=true %BUILD_METADATA% -o "!OUT!"

if !ERRORLEVEL! neq 0 (
    echo [ERROR] Theme Creator Linux framework-dependent build failed.
    set "ERR_LINUX=1"
    exit /b 1
)

del /q "!OUT!\*.pdb" >nul 2>&1
if exist "%ICON_PNG%" copy /y "%ICON_PNG%" "!OUT!\icon.png" >nul

echo [OK] Theme Creator Linux framework-dependent published to: !OUT!\
exit /b 0

:do_build_appimage
echo.
echo ==================================================
echo Building: Theme Creator Linux x64 AppImage
echo ==================================================
if not exist "%OUT_ROOT%\linux-x64-standalone\%BIN_NAME%" (
    echo [INFO] Linux x64 standalone build not found. Building prerequisite first...
    call :do_build_linux_standalone
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to build Linux x64 prerequisite for AppImage.
        set "ERR_APPIMAGE=1"
        exit /b 1
    )
)

REM WSL must exist AND have a distro with bash (wsl.exe alone is not enough)
set "HAS_WSL_BASH=0"
where wsl >nul 2>&1
if !ERRORLEVEL! equ 0 (
    wsl bash -c "exit 0" >nul 2>&1
    if !ERRORLEVEL! equ 0 set "HAS_WSL_BASH=1"
)
if "!HAS_WSL_BASH!"=="1" (
    echo [INFO] WSL detected. Packaging AppImage via build_creator_appimage.sh...
    wsl bash build_creator_appimage.sh "!APP_VER!"
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] AppImage generation encountered an error in WSL.
        set "ERR_APPIMAGE=1"
        exit /b 1
    )
    if exist "publish\releases\%RELEASE_NAME%_linux-x64.AppImage" (
        echo [OK] Theme Creator Linux x64 AppImage published:
        echo      - AppImage: publish\releases\%RELEASE_NAME%_linux-x64.AppImage
        exit /b 0
    )
) else (
    echo [WARN] WSL with a Linux distribution ^(bash^) is not available on this Windows host. AppImage skipped.
    echo        To build the AppImage locally, enable WSL or run build_creator_appimage.sh on Linux.
)
exit /b 0

:do_build_mac_arm64
call :build_mac "osx-arm64" "mac-arm64-standalone" "macOS_AppleSilicon" "ERR_MAC_ARM64" "macOS Apple Silicon ARM64"
exit /b %ERRORLEVEL%

:do_build_mac_x64
call :build_mac "osx-x64" "mac-x64-standalone" "macOS_Intel" "ERR_MAC_X64" "macOS Intel x64"
exit /b %ERRORLEVEL%

REM %1=RID %2=output folder %3=release suffix %4=error flag %5=label
:build_mac
echo.
echo ==================================================
echo Building: Theme Creator %~5 Standalone
echo ==================================================
set "MAC_DIR=%OUT_ROOT%\%~2"
set "APP_DIR=!MAC_DIR!\%APP_DISPLAY%.app"
set "TMP_DIR=%OUT_ROOT%\%~1-tmp"
if exist "!MAC_DIR!" rmdir /s /q "!MAC_DIR!" >nul 2>&1
mkdir "!APP_DIR!\Contents\MacOS" >nul 2>&1
mkdir "!APP_DIR!\Contents\Resources" >nul 2>&1

dotnet publish "%PROJECT_PATH%" -c Release -r %~1 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=false -p:EnableCompressionInSingleFile=true %BUILD_METADATA% -o "!TMP_DIR!"

if !ERRORLEVEL! neq 0 (
    echo [ERROR] Theme Creator %~5 build failed.
    set "%~4=1"
    exit /b 1
)

del /q "!TMP_DIR!\*.pdb" >nul 2>&1
xcopy /e /y /q "!TMP_DIR!\*" "!APP_DIR!\Contents\MacOS\" >nul
rmdir /s /q "!TMP_DIR!" >nul 2>&1

if exist "!APP_DIR!\Contents\MacOS\%BIN_NAME%" (
    copy /y "!APP_DIR!\Contents\MacOS\%BIN_NAME%" "!MAC_DIR!\%BIN_NAME%" >nul
)
if exist "%ICON_PNG%" copy /y "%ICON_PNG%" "!APP_DIR!\Contents\Resources\icon.png" >nul

> "!APP_DIR!\Contents\Info.plist" echo ^<?xml version="1.0" encoding="UTF-8"?^>
REM "!" in <!DOCTYPE> would be eaten by delayed expansion, so write this line with it disabled
setlocal DisableDelayedExpansion
>> "%APP_DIR%\Contents\Info.plist" echo ^<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"^>
endlocal
>> "!APP_DIR!\Contents\Info.plist" echo ^<plist version="1.0"^>
>> "!APP_DIR!\Contents\Info.plist" echo ^<dict^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleName^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>%APP_DISPLAY%^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleDisplayName^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>%APP_DISPLAY%^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleIdentifier^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>com.hotment.rbwrthemecreator^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleVersion^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>!NUMERIC_VER!^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleShortVersionString^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>!APP_VER!^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>NSHumanReadableCopyright^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>Copyright © 2026 Hotment^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundlePackageType^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>APPL^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>CFBundleExecutable^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<string^>%BIN_NAME%^</string^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<key^>NSHighResolutionCapable^</key^>
>> "!APP_DIR!\Contents\Info.plist" echo     ^<true/^>
>> "!APP_DIR!\Contents\Info.plist" echo ^</dict^>
>> "!APP_DIR!\Contents\Info.plist" echo ^</plist^>

> "!MAC_DIR!\run.command" echo #^^!/usr/bin/env bash
>> "!MAC_DIR!\run.command" echo DIR="$(cd "$(dirname "$0")" && pwd)"
>> "!MAC_DIR!\run.command" echo chmod +x "${DIR}/%APP_DISPLAY%.app/Contents/MacOS/%BIN_NAME%" 2^>/dev/null
>> "!MAC_DIR!\run.command" echo exec "${DIR}/%APP_DISPLAY%.app/Contents/MacOS/%BIN_NAME%" "$@"

powershell -NoProfile -Command "Compress-Archive -Path '!MAC_DIR!/*' -DestinationPath 'publish/releases/%RELEASE_NAME%_%~3.zip' -CompressionLevel Optimal -Force" >nul 2>&1

echo [OK] Theme Creator %~5 published:
echo      - Double-click App: '%APP_DISPLAY%.app'
echo      - Terminal binary: ./%BIN_NAME% (or run.command)
echo      - Zip Package: publish\releases\%RELEASE_NAME%_%~3.zip
exit /b 0

REM ============================================================================
REM Clean Procedure (only the Theme Creator output; overlay builds are kept)
REM ============================================================================

:do_clean
echo.
echo [CLEAN] Cleaning Theme Creator publish output...
if exist "%OUT_ROOT%" (
    rmdir /s /q "%OUT_ROOT%"
    echo [OK] %OUT_ROOT% removed.
) else (
    echo [INFO] %OUT_ROOT% does not exist. Nothing to clean.
)
del /q "publish\releases\%RELEASE_NAME%_*" >nul 2>&1
del /q "publish\releases\%BIN_NAME%_*" >nul 2>&1
echo [OK] Theme Creator release packages removed from publish\releases.
if "%~1"=="" pause
exit /b 0

REM ============================================================================
REM Build Completion Summary
REM ============================================================================

:build_finish
echo.
echo ==================================================
echo              THEME CREATOR BUILD SUMMARY
echo ==================================================

powershell -NoProfile -Command "$releases = Get-ChildItem -Path 'publish/releases' -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '%RELEASE_NAME%_*' -or $_.Name -like '%BIN_NAME%_*' }; if ($releases) { Write-Host '--- Theme Creator Packages Ready For Distribution ---' -ForegroundColor Cyan; $releases | Select-Object Name, @{Name='Size (MB)';Expression={[math]::Round($_.Length / 1MB, 2)}} | Format-Table -AutoSize } else { Write-Host 'No Theme Creator release files found in publish/releases.' }"

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
if defined ERR_LINUX (
    echo [!] Linux framework-dependent build encountered errors.
    set "HAS_FAILURES=1"
)
if defined ERR_APPIMAGE (
    echo [!] Linux x64 AppImage build encountered errors.
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
    echo ALL REQUESTED THEME CREATOR BUILDS COMPLETED SUCCESSFULLY.
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
echo   build_creator.bat [target]
echo.
echo Available Targets:
echo   all                 Build all release targets (Windows, Linux, macOS)
echo   win-standalone      Build Windows x64 standalone single-file (.exe - double-click to run)
echo   win-arm64           Build Windows ARM64 standalone single-file (Snapdragon / Surface Pro)
echo   windows             Build Windows framework-dependent (publish\creator\win-x64)
echo   linux-standalone    Build Linux x64 standalone (terminal ./RbwrThemeCreator, run.sh, .desktop)
echo   linux-arm64         Build Linux ARM64 standalone (Raspberry Pi 4/5)
echo   appimage            Build Linux x64 AppImage (.AppImage package via WSL or Linux)
echo   linux               Build Linux framework-dependent (publish\creator\linux-x64)
echo   mac-arm64           Build macOS Apple Silicon ARM64 standalone (.app + ./RbwrThemeCreator)
echo   mac-x64             Build macOS Intel x64 standalone (.app + ./RbwrThemeCreator)
echo   clean               Delete Theme Creator output (publish\creator + its release packages)
echo   help                Display this help screen
echo.
echo If run without arguments, an interactive menu is displayed.
exit /b 0
