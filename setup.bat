@echo off
setlocal enabledelayedexpansion

echo =======================================================
echo  Localized Agentic Memory Framework - Setup & Install
echo =======================================================
echo.

:: 1. Navigate to repository root regardless of launch location
cd /d "%~dp0"

:: 2. Check Python installation
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your system PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VER=%%i
echo [*] Detected %PYTHON_VER%

:: 3. Create Virtual Environment if not present
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment in .venv...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo Please ensure python-venv is available.
        pause
        exit /b 1
    )
) else (
    echo [*] Existing virtual environment found in .venv.
)

:: 4. Activate Virtual Environment
call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

:: 5. Install Dependencies
echo.
echo [*] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [*] Installing production dependencies from requirements.txt...
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install requirements.txt. Please check your internet connection.
    pause
    exit /b 1
)

echo.
echo [*] Installing development dependencies (pytest, matplotlib, ruff)...
pip install -r requirements-dev.txt
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Development dependencies could not be fully installed.
)

:: 6. Initialize Database Schema
echo.
echo [*] Initializing local database schema and migrations...
python -c "import sys; sys.path.insert(0, 'src'); import db; db.init_db(); print('Database schema verified.')"

:: 7. Check Ollama
echo.
echo [*] Checking local Ollama service...
where ollama >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] WARNING: 'ollama' command was not found in your PATH.
    echo     You can still run offline tests, but local LLM inference requires Ollama.
    echo     Download Ollama from: https://ollama.com/download
) else (
    for /f "tokens=*" %%i in ('ollama --version') do echo [*] Found %%i
    echo [*] Pulling recommended models (requires internet and running Ollama)...
    echo     Pulling %LAM_MODEL_CHAT:-qwen2.5:1.5b%...
    ollama pull qwen2.5:1.5b
    echo     Pulling %LAM_MODEL_EXTRACTION:-llama3.2:3b%...
    ollama pull llama3.2:3b
)

:: 8. Run Offline Verification Suite
echo.
echo [*] Running automated offline verification tests...
python -m pytest -q
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Some tests reported issues. Please check output above.
) else (
    echo [*] All offline verification tests PASSED!
)

echo.
echo =======================================================
echo  Setup Complete!
echo =======================================================
echo.
echo To start the web application:
echo   run.bat
echo.
echo To start the terminal CLI:
echo   .venv\Scripts\python.exe src\chat.py
echo.
pause