#!/bin/bash
# Create virtual environment and install dependencies for LeetBot

cd "$(dirname "$0")"

# Prefer Python 3.12 (py-cord has issues with Python 3.14's removed audioop)
PYTHON=${PYTHON:-$(command -v python3.12 2>/dev/null || command -v python3 2>/dev/null)}
if ! $PYTHON -c "import sys; exit(0 if sys.version_info < (3, 14) else 1)" 2>/dev/null; then
    echo "Warning: Python 3.14+ may have issues. Trying python3.12..."
    PYTHON=$(command -v python3.12 2>/dev/null || true)
fi

echo "Using: $PYTHON"
$PYTHON --version

echo ""
echo "Creating venv..."
rm -rf venv
$PYTHON -m venv venv

echo ""
echo "Installing dependencies..."
./venv/bin/pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

echo ""
echo "Done! Run the bot with:"
echo "  source venv/bin/activate && python run.py"
echo "Or:"
echo "  ./run.sh"
