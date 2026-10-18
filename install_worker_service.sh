#!/usr/bin/env bash
# ==============================================================================
# Ollama Agents - Distributed Compute Worker Node Systemd Service Installer
# Supports Raspberry Pi (Raspberry Pi OS / Debian), Ubuntu, and Linux distros.
# ==============================================================================

set -e

# Default settings
DEFAULT_SERVICE_NAME="ollama-worker"
DEFAULT_PORT=9000
DEFAULT_OLLAMA_PORT=11434
SERVICE_NAME="$DEFAULT_SERVICE_NAME"
WORKER_PORT="$DEFAULT_PORT"
OLLAMA_PORT="$DEFAULT_OLLAMA_PORT"
MASTER_URL=""
PYTHON_BIN=""
UNINSTALL=false

# Help message
show_help() {
    cat << EOF
Usage: sudo ./install_worker_service.sh [OPTIONS]

Install and start Ollama Agents Distributed Worker Node as a systemd service.

Options:
  --master <URL>        Master node URL to auto-register with
                        (e.g., http://192.168.29.13:8100)
  --port <PORT>         Worker node HTTP port (default: 9000)
  --ollama-port <PORT>  Local Ollama port (default: 11434)
  --service <NAME>      Systemd service name (default: ollama-worker)
  --python <PATH>       Path to Python binary (default: auto-detected)
  --uninstall           Stop, disable, and remove the worker service
  -h, --help            Show this help message

Examples:
  # Basic auto-install (mDNS LAN discovery):
  sudo ./install_worker_service.sh

  # Install with explicit Master server address:
  sudo ./install_worker_service.sh --master http://192.168.29.13:8100

  # Uninstall the service:
  sudo ./install_worker_service.sh --uninstall
EOF
}

# Parse command line flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --master)
            MASTER_URL="$2"
            shift 2
            ;;
        --port)
            WORKER_PORT="$2"
            shift 2
            ;;
        --ollama-port)
            OLLAMA_PORT="$2"
            shift 2
            ;;
        --service)
            SERVICE_NAME="$2"
            shift 2
            ;;
        --python)
            PYTHON_BIN="$2"
            shift 2
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            show_help
            exit 1
            ;;
    esac
done

# Ensure script is executed with root privileges
if [[ $EUID -ne 0 ]]; then
    echo "[!] This script must be run as root to configure systemd services."
    echo "[*] Elevating with sudo..."
    exec sudo bash "$0" "$@"
fi

# Locate the actual non-root user and home directory
if [[ -n "$SUDO_USER" && "$SUDO_USER" != "root" ]]; then
    TARGET_USER="$SUDO_USER"
    TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
else
    TARGET_USER="${USER:-root}"
    TARGET_HOME="${HOME:-/root}"
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
ALIAS_SERVICE_FILE="/etc/systemd/system/ollama-agents-worker.service"

# Handle uninstallation
if [[ "$UNINSTALL" = true ]]; then
    echo "==================================================="
    echo "  Uninstalling Ollama Agents Worker Service"
    echo "==================================================="
    
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        echo "[*] Stopping service '${SERVICE_NAME}'..."
        systemctl stop "${SERVICE_NAME}" || true
    fi

    if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        echo "[*] Disabling service '${SERVICE_NAME}'..."
        systemctl disable "${SERVICE_NAME}" || true
    fi

    if [[ -f "$SERVICE_FILE" ]]; then
        echo "[*] Removing service file: $SERVICE_FILE"
        rm -f "$SERVICE_FILE"
    fi

    if [[ -L "$ALIAS_SERVICE_FILE" || -f "$ALIAS_SERVICE_FILE" ]]; then
        echo "[*] Removing alias file: $ALIAS_SERVICE_FILE"
        rm -f "$ALIAS_SERVICE_FILE"
    fi

    systemctl daemon-reload
    echo "[✓] Worker service '${SERVICE_NAME}' completely removed."
    exit 0
fi

echo "==================================================="
echo "  Ollama Agents Worker Node Service Installer"
echo "==================================================="
echo " Target User:    $TARGET_USER"
echo " Target Home:    $TARGET_HOME"
echo " Service Name:   $SERVICE_NAME"
echo " Worker Port:    $WORKER_PORT"
echo " Local Ollama:   Port $OLLAMA_PORT"
if [[ -n "$MASTER_URL" ]]; then
    echo " Master URL:     $MASTER_URL"
else
    echo " Discovery:      LAN Auto-Discovery (mDNS UDP port 9999)"
fi
echo "==================================================="

# Detect Python interpreter
if [[ -z "$PYTHON_BIN" ]]; then
    # 1. Check local virtual environment in current directory
    if [[ -f "$PWD/.venv/bin/python3" ]]; then
        PYTHON_BIN="$PWD/.venv/bin/python3"
    # 2. Check virtualenv in target user's home directory
    elif [[ -f "$TARGET_HOME/ollama-agents/.venv/bin/python3" ]]; then
        PYTHON_BIN="$TARGET_HOME/ollama-agents/.venv/bin/python3"
    elif [[ -f "$TARGET_HOME/.venv/bin/python3" ]]; then
        PYTHON_BIN="$TARGET_HOME/.venv/bin/python3"
    # 3. Check system python3
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    else
        echo "[ERROR] python3 was not found on this system. Please install Python 3.9+ first."
        exit 1
    fi
fi

echo "[+] Using Python interpreter: $PYTHON_BIN"

# Verify python version >= 3.9
PY_VER="$($PYTHON_BIN -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
echo "[+] Detected Python version: $PY_VER"

# Check if required worker dependencies or ollama_agents package is installed
echo "[*] Verifying worker module dependencies..."
if ! "$PYTHON_BIN" -c "import ollama_agents.worker_node" 2>/dev/null; then
    echo "[!] 'ollama_agents.worker_node' is not yet installed in $PYTHON_BIN."
    
    # Check if we are inside the repository root
    if [[ -f "$PWD/pyproject.toml" && -d "$PWD/src/ollama_agents" ]]; then
        echo "[*] Detected repository at $PWD. Installing current repository in editable mode..."
        sudo -u "$TARGET_USER" "$PYTHON_BIN" -m pip install -e "$PWD"
    else
        echo "[*] Installing dependencies (fastapi uvicorn psutil pydantic)..."
        sudo -u "$TARGET_USER" "$PYTHON_BIN" -m pip install --upgrade fastapi uvicorn psutil pydantic
        # If ollama-agents is available via git or pip:
        echo "[*] Attempting to install ollama-agents via pip..."
        sudo -u "$TARGET_USER" "$PYTHON_BIN" -m pip install git+https://github.com/Goldking25/ollama-agents.git || true
    fi
fi

# Prepare ExecStart arguments
EXEC_ARGS="-m ollama_agents.worker_node --host 0.0.0.0 --port ${WORKER_PORT} --ollama-port ${OLLAMA_PORT}"
if [[ -n "$MASTER_URL" ]]; then
    EXEC_ARGS="${EXEC_ARGS} --master ${MASTER_URL}"
fi

# Create workspace directory for the worker node
WORKER_WORKSPACE="${TARGET_HOME}/ollama_workspace"
mkdir -p "$WORKER_WORKSPACE"
chown "$TARGET_USER":"$(id -gn "$TARGET_USER")" "$WORKER_WORKSPACE"

# Write systemd service file
echo "[*] Writing systemd service file to $SERVICE_FILE..."
cat << EOF > "$SERVICE_FILE"
[Unit]
Description=Ollama Agents Distributed Compute Worker Node
After=network-online.target ollama.service
Wants=network-online.target
Documentation=https://github.com/Goldking25/ollama-agents

[Service]
Type=simple
User=${TARGET_USER}
Group=$(id -gn "${TARGET_USER}")
WorkingDirectory=${TARGET_HOME}
Environment="PYTHONUNBUFFERED=1"
Environment="OLLAMA_HOST=0.0.0.0"
ExecStart=${PYTHON_BIN} ${EXEC_ARGS}
Restart=always
RestartSec=5
TimeoutStopSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SERVICE_FILE"

# Create alias link so 'ollama-agents-worker' and 'ollama-worker' can both be used
if [[ "$SERVICE_NAME" != "ollama-agents-worker" ]]; then
    ln -sf "$SERVICE_FILE" "$ALIAS_SERVICE_FILE"
fi

# Reload systemd daemon
echo "[*] Reloading systemd daemon (systemctl daemon-reload)..."
systemctl daemon-reload

# Enable service for auto-start on boot
echo "[*] Enabling ${SERVICE_NAME}.service on boot..."
systemctl enable "${SERVICE_NAME}.service"

# Restart service immediately
echo "[*] Starting ${SERVICE_NAME}.service..."
systemctl restart "${SERVICE_NAME}.service"

# Wait a brief moment to check service state
sleep 2

if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    echo ""
    echo "==================================================="
    echo "  [SUCCESS] Worker Service is ONLINE & RUNNING!   "
    echo "==================================================="
    echo "  Service Name:    ${SERVICE_NAME}.service"
    echo "  Listening on:    http://0.0.0.0:${WORKER_PORT}"
    echo "  Workspace:       ${WORKER_WORKSPACE}"
    echo "  Auto-Start:      Enabled on system boot"
    echo "==================================================="
    echo ""
    echo "Useful Management Commands:"
    echo "  • Check status:  sudo systemctl status ${SERVICE_NAME}"
    echo "  • View logs:     sudo journalctl -u ${SERVICE_NAME} -f"
    echo "  • Restart:       sudo systemctl restart ${SERVICE_NAME}"
    echo "  • Stop:          sudo systemctl stop ${SERVICE_NAME}"
    echo "  • Uninstall:     sudo bash $0 --uninstall"
    echo ""
else
    echo ""
    echo "[!] WARNING: Service '${SERVICE_NAME}' was installed, but is not currently active."
    echo "[*] Recent systemd logs for ${SERVICE_NAME}:"
    echo "---------------------------------------------------"
    journalctl -u "${SERVICE_NAME}.service" -n 25 --no-pager || true
    echo "---------------------------------------------------"
    echo "Check configuration with: sudo journalctl -u ${SERVICE_NAME} -f"
    exit 1
fi
