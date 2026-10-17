# Windows Installation and Setup Guide

This guide provides step-by-step instructions to set up, configure, test, and launch the **Localized Agentic Memory Framework** on Windows 10 and Windows 11.

---

## 1. Prerequisites

Before installing the framework, ensure you have:

1. **Python 3.10, 3.11, or 3.12:**
   - Download from [python.org](https://www.python.org/downloads/windows/).
   - **Crucial:** During installation, check the box:  
     `☑ Add python.exe to PATH`
2. **Ollama for Windows:**
   - Download and run the Windows installer from [ollama.com/download](https://ollama.com/download).
   - Once installed, Ollama runs in your system tray.
3. **Hardware Recommendations:**
   - 8 GB+ RAM (16 GB recommended for smooth multi-model local inference).
   - ~6 GB free disk space for local models (`qwen2.5:1.5b` ~1.0 GB, `llama3.2:3b` ~2.0 GB, Chroma embedding models ~100 MB).

---

## 2. Quick Automated Setup (Recommended)

1. Open File Explorer, navigate to the cloned project repository.
2. Double-click `setup.bat`.
3. The setup script will:
   - Verify Python and virtual environment.
   - Upgrade pip and install all production dependencies (`requirements.txt`).
   - Install testing and development packages (`requirements-dev.txt`).
   - Automatically initialize the SQLite canonical database schema.
   - Check the local Ollama service and pull the recommended AI models.
   - Run the automated offline verification test suite.

Once `setup.bat` finishes with `Setup Complete!`, launch the application:
- **Web Interface:** Double-click `run.bat` (opens in your default browser at `http://localhost:8501`).
- **Terminal CLI:** Open PowerShell in the project directory and run:
  ```powershell
  .\.venv\Scripts\python.exe src\chat.py
  ```

---

## 3. Manual Step-by-Step Installation

If you prefer to configure the environment manually via PowerShell:

### Step 1: Open Terminal in Project Directory
```powershell
cd "C:\Users\<YourUsername>\Code Projects\localized-agentic-memory-framework"
```

### Step 2: Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

*(If PowerShell displays an `ExecutionPolicy` error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` in that session).*

### Step 3: Install Required Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Step 4: Verify Ollama and Pull Local Models
Verify that the Ollama service is active:
```powershell
ollama --version
```
Pull the two designated project models:
```powershell
# Chat model (fast, conversational)
ollama pull qwen2.5:1.5b

# Extraction & conflict reasoning model
ollama pull llama3.2:3b
```

### Step 5: Initialize the Database
```powershell
python -c "from src import db; db.init_db(); print('Database initialized.')"
```

### Step 6: Run Offline Verification Tests
```powershell
python -m pytest -v
```
All offline unit tests should pass with zero failures.

---

## 4. Running the Application

### Web UI (Streamlit)
```powershell
streamlit run src/app.py
```
Or simply double-click `run.bat`.

### Command-Line REPL (CLI)
```powershell
python src/chat.py
```

### Running the Deduplication Benchmark
```powershell
# Run with live Ollama (if running)
python src/benchmark.py

# Run in deterministic offline evaluation mode
python src/benchmark.py --offline
```

---

## 5. Storage Locations & Configuration

By default on Windows, all runtime data is stored in your personal application data folder:
- **Default Database:** `%LOCALAPPDATA%\LocalizedAgenticMemory\memory.db`  
  (e.g., `C:\Users\<username>\AppData\Local\LocalizedAgenticMemory\memory.db`)
- **Default Vector Index:** `%LOCALAPPDATA%\LocalizedAgenticMemory\chroma\`
- **Memory Exports:** `%LOCALAPPDATA%\LocalizedAgenticMemory\exports\`

### Custom Directory Override
To store data in a custom folder, set the `LAM_DATA_DIR` environment variable before running:
```powershell
$env:LAM_DATA_DIR = "D:\MySecureAgenticData"
streamlit run src/app.py
```

---

## 6. Troubleshooting & Common Windows Issues

### Issue 1: `ollama: The term 'ollama' is not recognized`
- **Cause:** Ollama is not installed or its program folder was not added to your system PATH.
- **Fix:** Install Ollama from [ollama.com/download](https://ollama.com/download). If already installed, ensure `C:\Users\<username>\AppData\Local\Programs\Ollama` is in your environment PATH, or start the Ollama desktop app from the Start Menu.

### Issue 2: `ConnectionError: Failed to connect to Ollama`
- **Cause:** The Ollama background service is stopped.
- **Fix:** Open a terminal and run `ollama serve`, or launch the Ollama app from the Windows Start menu so its llama icon appears in the system tray.

### Issue 3: Streamlit Port 8501 Conflict
- **Cause:** Another application or previous Streamlit process is using port 8501.
- **Fix:** Launch Streamlit on a different port:
  ```powershell
  streamlit run src/app.py --server.port 8502
  ```

### Issue 4: PowerShell `Activate.ps1 cannot be loaded because running scripts is disabled`
- **Fix:** Run this command once in your PowerShell window:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\activate
  ```
