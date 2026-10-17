@echo off
setlocal

:: Navigate to repository directory regardless of where run.bat was called from
cd /d "%~dp0"

echo =======================================================
echo  Starting Localized Agentic Memory Framework
echo =======================================================
echo.

:: Check virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found in .venv.
    echo Please run setup.bat first to prepare the environment.
    echo.
    pause
    exit /b 1
)

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Quick check for Ollama running
where ollama >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] Notice: Ollama CLI not detected in PATH.
    echo     If Ollama is running in background/tray, the app will connect normally.
    echo.
)

:: Launch Streamlit app
echo [*] Launching Streamlit web interface...
streamlit run src/app.py

pause