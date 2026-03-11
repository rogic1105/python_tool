@echo off
setlocal

:: ============================================================
::  Python Tool Launcher - Windows
::  Find conda, activate base environment, then launch ui.py
:: ============================================================

set CONDA_ACTIVATE=

:: Check common conda install locations (no quotes around paths - avoid double-quote issue)
for %%C in (
    %USERPROFILE%\miniconda3\Scripts\activate.bat
    %USERPROFILE%\anaconda3\Scripts\activate.bat
    %LOCALAPPDATA%\miniconda3\Scripts\activate.bat
    %LOCALAPPDATA%\anaconda3\Scripts\activate.bat
    C:\miniconda3\Scripts\activate.bat
    C:\anaconda3\Scripts\activate.bat
    C:\ProgramData\miniconda3\Scripts\activate.bat
    C:\ProgramData\anaconda3\Scripts\activate.bat
) do (
    if not defined CONDA_ACTIVATE (
        if exist "%%C" set CONDA_ACTIVATE=%%C
    )
)

:: Fallback: find conda.exe in PATH and derive activate.bat path
if not defined CONDA_ACTIVATE (
    where conda >nul 2>&1
    if %ERRORLEVEL%==0 (
        for /f "delims=" %%P in ('where conda') do (
            if not defined CONDA_ACTIVATE (
                set CONDA_ACTIVATE=%%~dpPactivate.bat
            )
        )
    )
)

if not defined CONDA_ACTIVATE (
    echo [ERROR] conda not found. Please install Miniconda or Anaconda.
    echo Tried locations:
    echo   %USERPROFILE%\miniconda3 / anaconda3
    echo   %LOCALAPPDATA%\miniconda3 / anaconda3
    echo   C:\miniconda3 / anaconda3
    pause
    exit /b 1
)

echo [OK] Found conda: %CONDA_ACTIVATE%
echo [..] Activating conda base environment...
call "%CONDA_ACTIVATE%" base

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate conda base environment.
    pause
    exit /b 1
)

echo [OK] Environment ready. Launching Python Tool UI...
echo.

cd /d "%~dp0"
python ui.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] ui.py exited with code %ERRORLEVEL%
    pause
)

endlocal
