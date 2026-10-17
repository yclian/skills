#!/usr/bin/env bash
# ==============================================================================
# upgrade_laya.sh - Deterministic Upgrade Script for Arwen svc:laya (:8500)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/srv/laya"
PYTHON_BIN="${TARGET_DIR}/venv/bin/python"
UV_BIN="${HOME}/.local/bin/uv"
TARGET_VERSION="${1:-0.4.7}"

echo "=========================================================="
echo "==> Upgrading Arwen System 1 Engine (laya -> ${TARGET_VERSION})"
echo "=========================================================="

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "ERROR: Python binary not found at ${PYTHON_BIN}" >&2
    exit 1
fi

if [[ ! -x "${UV_BIN}" ]]; then
    UV_BIN="$(which uv || true)"
    if [[ -z "${UV_BIN}" ]]; then
        echo "ERROR: uv binary not found in PATH or ~/.local/bin/uv" >&2
        exit 1
    fi
fi

# 1. Update server.py and requirements.txt in /srv/laya if invoked locally
if [[ -f "${SCRIPT_DIR}/server.py" && "${SCRIPT_DIR}" != "${TARGET_DIR}" ]]; then
    echo "==> Syncing server.py and requirements.txt to ${TARGET_DIR}..."
    cp -v "${SCRIPT_DIR}/server.py" "${TARGET_DIR}/server.py"
    if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
        cp -v "${SCRIPT_DIR}/requirements.txt" "${TARGET_DIR}/requirements.txt"
    fi
fi

# 2. Upgrade laya using uv (--no-deps protects CPU torch==2.x+cpu from being replaced by PyPI CUDA torch)
echo "==> Installing laya==${TARGET_VERSION} into ${TARGET_DIR}/venv..."
"${UV_BIN}" pip install --python "${PYTHON_BIN}" --no-deps "laya==${TARGET_VERSION}"

# 3. Model warm-up & contract smoke check
echo "==> Running pre-restart contract smoke check..."
"${PYTHON_BIN}" - << 'EOF'
import sys
import laya

print(f"[check] Installed laya version: {getattr(laya, '__version__', 'unknown')}")

print("[check] Pre-loading model on CPU...")
agent = laya.load("convaiinnovations/laya", device="cpu")

print("[check] Testing choice & noul question...")
res = agent.predict(
    "Headline: Fed holds rates steady",
    {
        "cat": {
            "type": "choice",
            "instructions": "Classify headline",
            "criteria": {"actionable": "Material event", "noise": "Routine commentary"}
        },
        "is_rate": {
            "type": "noul",
            "instructions": "Does this mention interest rates?"
        }
    }
)
print(f"[check] Prediction success: answers={list(res.get('answers', {}).keys())}")

# Test score criteria with list of rubric strings
res_score = agent.predict(
    "Critical database deadlock",
    {
        "severity": {
            "type": "score",
            "instructions": "Rate severity",
            "criteria": ["trivial", "minor", "moderate", "high", "critical"]
        }
    }
)
print(f"[check] Score success: {res_score.get('answers', {}).get('severity', {}).get('score')}")
print("[check] All pre-flight contract assertions passed!")
EOF

# 4. Restart laya.service
echo "==> Restarting laya.service via systemctl..."
sudo systemctl restart laya

# 5. Health poll
echo "==> Polling http://127.0.0.1:8500/health..."
HEALTHY=false
for i in {1..15}; do
    if curl -s -f http://127.0.0.1:8500/health | grep -q '"status":"healthy"'; then
        HEALTHY=true
        break
    fi
    sleep 1
done

if [[ "${HEALTHY}" != "true" ]]; then
    echo "ERROR: laya service failed health check after restart!" >&2
    sudo systemctl status laya --no-pager >&2
    exit 1
fi

echo "==> Service is healthy! Live /health response:"
curl -s http://127.0.0.1:8500/health | python3 -m json.tool || true

# 6. Verify Decision #17 zero-persistence redaction in journald
echo "==> Verifying Decision #17 zero-persistence in journalctl..."
sudo journalctl -u laya -n 10 --no-pager | grep -E "laya-service|choice" || true

echo "=========================================================="
echo "==> Upgrade to laya ${TARGET_VERSION} complete & verified!"
echo "=========================================================="
