#!/usr/bin/env bash
set -e  # Exit on any error

ENV_NAME="superpixel_labeling"
VENV_DIR=".venv"

# --- Check if Python is installed ---
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python is not installed or not found in PATH."
    echo "Please install Python 3.12 and try again."
    exit 1
fi

# --- Check Python version ---
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.12"

if [[ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]]; then
    echo "⚠️ Warning: Detected Python $PYTHON_VERSION. This project is tested with Python 3.12."
    echo "    Proceeding anyway, but results may vary."
fi

# --- Create virtual environment ---
echo "Creating virtual environment in '$VENV_DIR'..."
python3 -m venv "$VENV_DIR"

# --- Activate virtual environment ---
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# --- Upgrade pip ---
echo "Upgrading pip..."
pip install --upgrade pip

# --- Install dependencies ---
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# --- Register Jupyter kernel ---
echo "Registering Jupyter kernel..."
python -m ipykernel install --user --name "$ENV_NAME" --display-name "Python ($ENV_NAME)"

# --- Final message ---
echo "✅ Setup complete."
echo "To activate the environment, run:"
echo "  source $VENV_DIR/bin/activate"
