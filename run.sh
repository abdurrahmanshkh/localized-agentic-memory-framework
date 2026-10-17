#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -f ".venv/bin/activate" ]; then
    echo "[ERROR] Virtual environment not found. Please run ./setup.sh first."
    exit 1
fi

source .venv/bin/activate

echo "[*] Launching Streamlit web application..."
streamlit run src/app.py
