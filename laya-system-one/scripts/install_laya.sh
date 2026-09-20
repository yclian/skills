#!/usr/bin/env bash
# ==============================================================================
# install_laya.sh - 1-Command Automated Installer for Laya System 1 Decision Engine
# ==============================================================================
# Sets up a lightweight (~842MB RAM) non-autoregressive decision engine on CPU.
# Compatible with Ubuntu 20.04+, Debian 11+, Linux Mint, and WSL2.
# ==============================================================================

set -euo pipefail

INSTALL_DIR="${LAYA_INSTALL_DIR:-/srv/laya}"
SERVICE_USER="${LAYA_USER:-$USER}"
SERVICE_PORT="${LAYA_PORT:-8500}"

echo "================================================================="
echo " Installing Laya System 1 Decision Engine (ModernBERT-large 395M)"
echo " Target Directory: ${INSTALL_DIR}"
echo " Port:             ${SERVICE_PORT}"
echo " User:             ${SERVICE_USER}"
echo "================================================================="

# 1. Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "[1/5] Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# 2. Create Target Directory
echo "[2/5] Creating installation directory..."
sudo mkdir -p "${INSTALL_DIR}"
sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

# 3. Create Virtualenv and Install Dependencies
echo "[3/5] Setting up Python 3.10+ virtualenv via uv..."
cd "${INSTALL_DIR}"
uv venv --python 3.10 "${INSTALL_DIR}/venv"

echo "[3/5] Installing PyTorch (CPU-only, ultra-light) and Laya..."
"${INSTALL_DIR}/venv/bin/uv" pip install \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.1.0"

"${INSTALL_DIR}/venv/bin/uv" pip install \
    "laya>=0.3.4" \
    "transformers>=4.40.0" \
    "fastapi>=0.110.0" \
    "uvicorn[standard]>=0.28.0" \
    "mcp>=1.2.0" \
    "pydantic>=2.0.0"

# 4. Copy Server Script
echo "[4/5] Deploying Laya server script..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/server.py" ]; then
    cp "${SCRIPT_DIR}/server.py" "${INSTALL_DIR}/server.py"
fi

# 5. Pre-warm Model Weights
echo "[5/5] Preloading ModernBERT-large weights (cached to ~/.cache/huggingface)..."
"${INSTALL_DIR}/venv/bin/python3" -c "import laya; print('Downloading/verifying weights...'); agent = laya.load('convaiinnovations/laya', device='cpu'); print('Model weights ready!')"

# Optional: Install Systemd Service if running as root or with sudo
if command -v systemctl &> /dev/null && [ -d /etc/systemd/system ]; then
    echo "Creating systemd service /etc/systemd/system/laya.service..."
    sudo tee /etc/systemd/system/laya.service > /dev/null <<EOF
[Unit]
Description=Laya Fast Non-Autoregressive Decision Engine & MCP Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=HOME=${HOME}
ExecStart=${INSTALL_DIR}/venv/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port ${SERVICE_PORT}
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable laya.service
    sudo systemctl restart laya.service
    echo "Laya systemd service started and enabled on boot!"
else
    echo "Systemd not detected. To start manually, run:"
    echo "  ${INSTALL_DIR}/venv/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port ${SERVICE_PORT}"
fi

echo "================================================================="
echo " Laya Installation Complete!"
echo " Health check: curl http://127.0.0.1:${SERVICE_PORT}/health"
echo " MCP Gateway:  http://127.0.0.1:${SERVICE_PORT}/mcp"
echo "================================================================="
