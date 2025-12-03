#!/bin/bash
# bundle_python.sh - Create bundled Python environment for SSTV Station
#
# This script creates a minimal Python venv with all required dependencies
# for distribution with the Tauri app.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_SRC="$PROJECT_ROOT/core/python"
TAURI_RESOURCES="$PROJECT_ROOT/sstv-station/src-tauri/resources/python"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================"
echo "SSTV Station - Python Bundle Creator"
echo "======================================"

# Check Python version
echo -n "Checking Python version... "
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    echo -e "${RED}FAILED${NC}"
    echo "Error: Python 3.9+ required, found $PYTHON_VERSION"
    exit 1
fi
echo -e "${GREEN}OK${NC} (Python $PYTHON_VERSION)"

# Create temp directory for building
TEMP_DIR=$(mktemp -d)
echo "Working directory: $TEMP_DIR"

cleanup() {
    echo "Cleaning up temp directory..."
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

# Create fresh venv
echo -n "Creating virtual environment... "
python3 -m venv "$TEMP_DIR/venv"
echo -e "${GREEN}OK${NC}"

# Activate venv and install dependencies
echo "Installing dependencies..."
source "$TEMP_DIR/venv/bin/activate"

# Upgrade pip first (suppress output)
pip install --upgrade pip -q

# Install production requirements
pip install -r "$PYTHON_SRC/requirements-prod.txt" -q
echo -e "${GREEN}Dependencies installed${NC}"

# Deactivate venv
deactivate

# Copy sstv_engine package to venv
echo -n "Copying sstv_engine package... "
cp -r "$PYTHON_SRC/sstv_engine" "$TEMP_DIR/venv/lib/python$PYTHON_VERSION/site-packages/"
echo -e "${GREEN}OK${NC}"

# Strip unnecessary files
echo -n "Stripping unnecessary files... "
find "$TEMP_DIR/venv" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$TEMP_DIR/venv" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$TEMP_DIR/venv" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "$TEMP_DIR/venv" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
find "$TEMP_DIR/venv" -type d -name ".git" -exec rm -rf {} + 2>/dev/null || true
# Remove pip cache and installer files
rm -rf "$TEMP_DIR/venv/lib/python$PYTHON_VERSION/site-packages/pip"* 2>/dev/null || true
rm -rf "$TEMP_DIR/venv/lib/python$PYTHON_VERSION/site-packages/setuptools"* 2>/dev/null || true
rm -rf "$TEMP_DIR/venv/lib/python$PYTHON_VERSION/site-packages/pkg_resources"* 2>/dev/null || true
rm -rf "$TEMP_DIR/venv/lib/python$PYTHON_VERSION/site-packages/wheel"* 2>/dev/null || true
echo -e "${GREEN}OK${NC}"

# Calculate size before copying
BUNDLE_SIZE=$(du -sh "$TEMP_DIR/venv" | cut -f1)
echo "Bundle size: $BUNDLE_SIZE"

# Create target directory and copy
echo -n "Copying to Tauri resources... "
rm -rf "$TAURI_RESOURCES"
mkdir -p "$TAURI_RESOURCES"
cp -r "$TEMP_DIR/venv"/* "$TAURI_RESOURCES/"
echo -e "${GREEN}OK${NC}"

# Verify the bundle works
echo -n "Verifying bundle... "
PYTHONPATH="$TAURI_RESOURCES/lib/python$PYTHON_VERSION/site-packages" \
    "$TAURI_RESOURCES/bin/python3" -c "import sstv_engine; print('OK')" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Bundle verified${NC}"
else
    echo -e "${RED}Bundle verification failed${NC}"
    exit 1
fi

echo ""
echo "======================================"
echo -e "${GREEN}Bundle created successfully!${NC}"
echo "Location: $TAURI_RESOURCES"
echo "Size: $BUNDLE_SIZE"
echo "======================================"
