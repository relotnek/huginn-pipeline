#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${HUGINN_VENV:-$HOME/.huginn-venv}"
BIN_DIR="${HOME}/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="${SCRIPT_DIR}/huginn"

echo "==> Installing Huginn"

# Ensure python3 is available
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found. Install Python 3.11+ first."
    exit 1
fi

# Check Python version
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "Error: Python 3.11+ required (found ${PY_VERSION})"
    exit 1
fi

# Create or reuse venv
if [ -d "$VENV_DIR" ]; then
    echo "    Using existing venv at ${VENV_DIR}"
else
    echo "    Creating venv at ${VENV_DIR}"
    python3 -m venv "$VENV_DIR"
fi

# Install into venv
echo "    Installing package from ${PKG_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -e "$PKG_DIR" --quiet

# Symlink into ~/.local/bin
mkdir -p "$BIN_DIR"
ln -sf "${VENV_DIR}/bin/huginn" "${BIN_DIR}/huginn"

# Verify
if "${BIN_DIR}/huginn" --version &>/dev/null; then
    VERSION=$("${BIN_DIR}/huginn" --version)
    echo ""
    echo "==> Huginn installed (${VERSION})"
    echo "    Binary: ${BIN_DIR}/huginn"
    echo "    Venv:   ${VENV_DIR}"
else
    echo ""
    echo "==> Huginn installed to ${BIN_DIR}/huginn"
    echo "    Venv: ${VENV_DIR}"
fi

# Check if ~/.local/bin is on PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    echo ""
    echo "    NOTE: ${BIN_DIR} is not on your PATH."
    echo "    Add this to your shell profile (~/.bashrc or ~/.zshrc):"
    echo ""
    echo "        export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "    Next: huginn --help"
