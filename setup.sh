#!/usr/bin/env bash
set -e

echo "======================================================="
echo " Localized Agentic Memory Framework - Setup & Install"
echo "======================================================="

# Navigate to script directory
cd "$(dirname "$0")"

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found. Please install Python 3.10+."
    exit 1
fi

echo "[*] Python: $(python3 --version)"

# Create virtual environment if missing
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Upgrade pip and install
echo "[*] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Init DB
echo "[*] Initializing database schema..."
python -c "import sys; sys.path.insert(0, 'src'); import db; db.init_db(); print('Database schema verified.')"

# Check Ollama
if command -v ollama &> /dev/null; then
    echo "[*] Ollama found: $(ollama --version)"
    echo "[*] Pulling recommended models..."
    ollama pull qwen2.5:1.5b || true
    ollama pull llama3.2:3b || true
else
    echo "[!] Ollama not found in PATH. Download from: https://ollama.com/download"
fi

# Run offline test suite
echo "[*] Running offline tests..."
python -m pytest -q

echo "======================================================="
echo " Setup Complete! Run with: ./run.sh"
echo "======================================================="
