@echo off
title RBWR Overlay Compiler
echo ==================================================
echo       RBWR OVERLAY EXECUTABLE COMPILER (NUITKA)
echo ==================================================
echo.

:: Step 1: Check and install compilation dependencies
echo [1/3] Ensuring required packages are installed...

if exist "venv\Scripts\activate.bat" (
    echo [INFO] Local virtual environment [venv] detected. Activating...
    call venv\Scripts\activate.bat
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Failed to install required Python packages!
    echo Please make sure Python is installed and added to PATH.
    pause
    exit /b %ERRORLEVEL%
)
echo.

:: Free file locks by terminating any running instances of rbwr_overlay
echo [1.5/3] Freeing file locks from any running overlay instances...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*rbwr_overlay*' -or $_.CommandLine -like '*RBWR_APRM_Calculator*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
if exist "rbwr_overlay.build" rmdir /s /q "rbwr_overlay.build" >nul 2>&1
if exist "rbwr_overlay.onefile-build" rmdir /s /q "rbwr_overlay.onefile-build" >nul 2>&1
echo [OK] All file locks freed successfully.
echo.

:: Step 2: Generate default icons programmatically before compiling
echo [2/3] Generating default custom icons...
python -c "import rbwr_overlay; rbwr_overlay.generate_default_icon()"
if not exist "icon.ico" (
    echo [WARN] Custom icon.ico not found, compilation will proceed with fallback icon.
) else (
    echo [OK] High-quality custom icons loaded successfully.
)
echo.
:: Step 2.5: Ask user for version and format
echo.
echo [2.5/3] Configuring version and package format...
set "CURRENT_VERSION=1.0.0"
python -c "import re; m = re.search(r'\n__version__\s*=\s*[\x22\x27](.*?)[\x22\x27]', open('rbwr_overlay.py', 'r', encoding='utf-8').read()); open('temp_ver.txt', 'w').write(m.group(1) if m else '1.0.0')"
if exist temp_ver.txt (
    set /p CURRENT_VERSION=<temp_ver.txt
    del temp_ver.txt
)

echo Current version detected in rbwr_overlay.py: %CURRENT_VERSION%
set /p VERSION="Enter new version (press Enter to keep %CURRENT_VERSION%): "
if "%VERSION%"=="" (
    set "VERSION=%CURRENT_VERSION%"
) else (
    python -c "import re; fp = 'rbwr_overlay.py'; content = open(fp, 'r', encoding='utf-8').read(); content = re.sub(r'__version__\s*=\s*[\x22\x27][^\x22\x27]+[\x22\x27]', '__version__ = \x22%VERSION%\x22', content); open(fp, 'w', encoding='utf-8').write(content)"
)

echo.
echo Select compilation format:
echo [1] Single-file Executable (.exe) [Default]
echo [2] Standalone Folder compressed (.zip)
echo [3] Both Single-file Executable and Portable Zip
echo [4] Test packaging logic (Mock Nuitka dry-run)
set /p FORMAT_OPT="Enter choice [1-4]: "

set "DRY_RUN=0"
if "%FORMAT_OPT%"=="4" goto mock_menu
if "%FORMAT_OPT%"=="3" goto format_both
if "%FORMAT_OPT%"=="2" goto format_zip
goto format_exe

:mock_menu
set "DRY_RUN=1"
echo.
echo Select format to mock:
echo [1] Single-file Executable (.exe)
echo [2] Standalone Folder compressed (.zip)
set /p MOCK_OPT="Enter choice [1-2]: "
if "%MOCK_OPT%"=="2" (
    call :do_compile zip
) else (
    call :do_compile exe
)
goto end_success

:format_both
call :do_compile exe
if %ERRORLEVEL% neq 0 goto end_failed
call :do_compile zip
if %ERRORLEVEL% neq 0 goto end_failed
goto end_success

:format_zip
call :do_compile zip
if %ERRORLEVEL% neq 0 goto end_failed
goto end_success

:format_exe
call :do_compile exe
if %ERRORLEVEL% neq 0 goto end_failed
goto end_success

:do_compile
set "FORMAT=%~1"
if "%FORMAT%"=="zip" (
    set "NUITKA_PARAMS=--standalone --output-filename=RBWR_APRM_Calculator.exe"
    set "OUTPUT_PARAM="
) else (
    set "NUITKA_PARAMS=--standalone --onefile"
    set "OUTPUT_PARAM=--output-filename=RBWR_APRM_Calculator_win_x64_v%VERSION%.exe"
)

echo.
:: Clean up old files and directories for this target
if "%FORMAT%"=="zip" (
    if exist "rbwr_overlay.build" rmdir /s /q "rbwr_overlay.build" >nul 2>&1
    if exist "rbwr_overlay.dist" rmdir /s /q "rbwr_overlay.dist" >nul 2>&1
    if exist "RBWR_APRM_Calculator_win_x64_v%VERSION%" rmdir /s /q "RBWR_APRM_Calculator_win_x64_v%VERSION%" >nul 2>&1
    if exist "RBWR_APRM_Calculator_win_x64_v%VERSION%.zip" del /f /q "RBWR_APRM_Calculator_win_x64_v%VERSION%.zip" >nul 2>&1
) else (
    if exist "rbwr_overlay.onefile-build" rmdir /s /q "rbwr_overlay.onefile-build" >nul 2>&1
    if exist "RBWR_APRM_Calculator_win_x64_v%VERSION%.exe" del /f /q "RBWR_APRM_Calculator_win_x64_v%VERSION%.exe" >nul 2>&1
)

:: Step 3: Trigger Nuitka high-fidelity compilation or Mock Dry-Run
if "%DRY_RUN%"=="1" (
    echo [DRY-RUN] Simulating Nuitka compilation outputs...
    echo       - Version: %VERSION%
    echo       - Format: %FORMAT%
    if "%FORMAT%"=="zip" (
        if not exist "rbwr_overlay.dist" mkdir "rbwr_overlay.dist"
        echo Mock executable > "rbwr_overlay.dist\RBWR_APRM_Calculator.exe"
    ) else (
        echo Mock executable > "RBWR_APRM_Calculator_win_x64_v%VERSION%.exe"
    )
    cmd /c exit 0
) else (
    echo [3/3] Compiling to a high-speed, GUI application...
    echo       - Version: %VERSION%
    echo       - Format: %FORMAT%
    echo       - Nuitka mode: %NUITKA_PARAMS%
    echo       - Console: Attach (runs silently in GUI mode)
    echo       - CPU cores: Utilizing ALL threads (--jobs=%NUMBER_OF_PROCESSORS%)
    echo.
    python -m nuitka %NUITKA_PARAMS% --windows-console-mode=attach --windows-icon-from-ico=icon.ico --windows-company-name="Hotment" --windows-product-name="RBWR APRM Calculator" --windows-file-description="RBWR APRM Calculator Overlay" --windows-file-version=%VERSION% --windows-product-version=%VERSION% --jobs=%NUMBER_OF_PROCESSORS% --enable-plugin=tk-inter %OUTPUT_PARAM% rbwr_overlay.py
)

if %ERRORLEVEL% neq 0 exit /b 1

echo.
if "%FORMAT%"=="zip" goto package_zip
goto package_exe

:package_zip
echo [INFO] Standalone folder compiled. Packaging into zip...
if exist "rbwr_overlay.dist" (
    if exist "RBWR_APRM_Calculator_win_x64_v%VERSION%" rmdir /s /q "RBWR_APRM_Calculator_win_x64_v%VERSION%"
    rename "rbwr_overlay.dist" "RBWR_APRM_Calculator_win_x64_v%VERSION%"
    goto do_zip
)
if exist "RBWR_APRM_Calculator_win_x64_v%VERSION%.dist" (
    if exist "RBWR_APRM_Calculator_win_x64_v%VERSION%" rmdir /s /q "RBWR_APRM_Calculator_win_x64_v%VERSION%"
    rename "RBWR_APRM_Calculator_win_x64_v%VERSION%.dist" "RBWR_APRM_Calculator_win_x64_v%VERSION%"
    goto do_zip
)
if exist "RBWR_APRM_Calculator_win_x64_v%VERSION%" (
    goto do_zip
)
echo [ERROR] Expected build directory not found!
pause
exit /b 1

:do_zip
python -c "import shutil; shutil.make_archive('RBWR_APRM_Calculator_win_x64_v%VERSION%', 'zip', 'RBWR_APRM_Calculator_win_x64_v%VERSION%')"
rmdir /s /q "RBWR_APRM_Calculator_win_x64_v%VERSION%"
echo [OK] Packaged standalone folder into RBWR_APRM_Calculator_win_x64_v%VERSION%.zip
exit /b 0

:package_exe
echo [OK] Release package compiled successfully.
if exist "RBWR_APRM_Calculator_win_x64_v%VERSION%.exe" (
    copy /y "RBWR_APRM_Calculator_win_x64_v%VERSION%.exe" "RBWR_APRM_Calculator.exe" >nul
)
exit /b 0

:end_success
echo.
echo ==================================================
echo COMPILATION COMPLETED SUCCESSFULLY!
echo ==================================================
pause
exit /b 0

:end_failed
echo.
echo ==================================================
echo COMPILATION FAILED!
echo Please verify that a C/C++ compiler, such as MSVC or MinGW, is installed.
echo ==================================================
pause
exit /b 1