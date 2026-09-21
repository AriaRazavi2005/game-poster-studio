@echo off
setlocal enabledelayedexpansion

:: ==============================================================================
:: Game Poster Studio — 1-Click Windows Desktop Launcher
:: ==============================================================================

:: 1. Force working directory to the directory containing this batch script
cd /d "%~dp0"
title Game Poster Studio

:: Visual Banner
echo ==============================================================================
echo   Game Poster Studio - Desktop Studio Launcher
echo ==============================================================================
echo.

:: 2. Virtual Environment Detection & Activation
set "VENV_ACTIVATED=0"
set "PYTHON_CMD="

if exist "%~dp0.venv\Scripts\activate.bat" (
    echo [*] Detected virtual environment: .venv
    call "%~dp0.venv\Scripts\activate.bat"
    set "PYTHON_CMD=python"
    set "VENV_ACTIVATED=1"
) else if exist "%~dp0venv\Scripts\activate.bat" (
    echo [*] Detected virtual environment: venv
    call "%~dp0venv\Scripts\activate.bat"
    set "PYTHON_CMD=python"
    set "VENV_ACTIVATED=1"
) else if exist "%~dp0env\Scripts\activate.bat" (
    echo [*] Detected virtual environment: env
    call "%~dp0env\Scripts\activate.bat"
    set "PYTHON_CMD=python"
    set "VENV_ACTIVATED=1"
)

:: 3. Python Discovery (if not already set by venv)
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=python"
    ) else (
        where py >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_CMD=py -3"
        ) else (
            goto PYTHON_NOT_FOUND
        )
    )
)

:: Verify Python executable runs and retrieve version
for /f "tokens=*" %%v in ('!PYTHON_CMD! --version 2^>^&1') do set "PY_VER=%%v"
echo [*] Using Python: !PY_VER!

:: 4. Dependency Verification & Bootstrapping
echo [*] Verifying dependencies: Pillow, numpy, customtkinter...

!PYTHON_CMD! -c "import PIL, numpy, customtkinter" >nul 2>&1
if !errorlevel! equ 0 (
    echo [*] All required packages are present.
    goto LAUNCH_APP
)

echo.
echo [*] Optional GUI package (customtkinter) is not installed.
echo     Pillow and numpy are active; customtkinter provides Windows 11 styling.
echo.

if exist "%~dp0requirements.txt" (
    echo A requirements.txt file was found in the project directory.
    set "INSTALL_PROMPT=y"
    set /p "INSTALL_PROMPT=Would you like to install required packages now? [Y/n]: "
    if /i "!INSTALL_PROMPT!"=="n" (
        echo [-] Dependency installation skipped by user.
        echo [*] Launching GUI with native Tkinter fallback...
        goto LAUNCH_APP
    )

    echo.
    echo [*] Installing dependencies via pip...
    !PYTHON_CMD! -m pip install -r "%~dp0requirements.txt"
    if !errorlevel! neq 0 (
        echo.
        echo [WARNING] Failed to install packages via pip.
        echo Launching with native Tkinter fallback...
        goto LAUNCH_APP
    )
    echo [*] Dependencies installed successfully.
) else (
    echo [*] requirements.txt not found. Attempting direct installation...
    !PYTHON_CMD! -m pip install Pillow numpy customtkinter
)

:: 5. Launch Application
:LAUNCH_APP
echo.
echo [*] Launching Game Poster Studio GUI...
echo.

if exist "%~dp0gui.py" (
    !PYTHON_CMD! "%~dp0gui.py" %*
) else (
    !PYTHON_CMD! -m poster_studio.gui.main_window %*
)

set "APP_EXIT_CODE=!errorlevel!"
if !APP_EXIT_CODE! neq 0 (
    echo.
    echo ==============================================================================
    echo [ERROR] Game Poster Studio terminated unexpectedly - exit code: !APP_EXIT_CODE!
    echo See above for diagnostic traceback.
    echo ==============================================================================
    goto ERROR_EXIT
)

goto CLEAN_EXIT

:: Diagnostic Error Handlers
:PYTHON_NOT_FOUND
echo.
echo ==============================================================================
echo [FATAL ERROR] Python was not found on your system or is not in your PATH.
echo.
echo To resolve this:
echo   1. Download Python 3.11 or newer from: https://www.python.org/downloads/
echo   2. During installation, CHECK the box: "Add python.exe to PATH"
echo   3. Restart this launcher or open a new terminal window.
echo ==============================================================================
goto ERROR_EXIT

:ERROR_EXIT
echo.
:: In automated runs, CI/CD, or when arguments are passed, exit without hanging on pause
if not "%~1"=="" goto SKIP_PAUSE
if defined CI goto SKIP_PAUSE
if defined GITHUB_ACTIONS goto SKIP_PAUSE
if defined TF_BUILD goto SKIP_PAUSE
if defined CONTINUOUS_INTEGRATION goto SKIP_PAUSE
if defined NON_INTERACTIVE goto SKIP_PAUSE

:: Only pause if started via Windows Explorer (no arguments and invoked by cmd.exe /c)
echo %cmdcmdline% | findstr /i /c:"%~nx0" >nul
if !errorlevel! equ 0 (
    echo Press any key to exit...
    pause >nul
)

:SKIP_PAUSE
exit /b 1

:CLEAN_EXIT
endlocal
exit /b 0
