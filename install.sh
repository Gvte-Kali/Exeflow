#!/usr/bin/env bash
# ─────────────────────────────────────────────
#  ExeFlow — Installer
#  Compatible: apt · pacman · dnf · zypper · apk
#  Usage: sudo bash install.sh
# ─────────────────────────────────────────────

set -e

EXEFLOW_URL="https://raw.githubusercontent.com/Gvte-Kali/Exeflow/refs/heads/main/exeflow.py"
INSTALL_DIR="/opt/exeflow"
BIN_LINK="/usr/local/bin/exeflow"

GREEN="\033[0;32m"
CYAN="\033[0;36m"
AMBER="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { echo -e "${CYAN}[*]${RESET} $1"; }
ok()    { echo -e "${GREEN}[✓]${RESET} $1"; }
warn()  { echo -e "${AMBER}[!]${RESET} $1"; }
err()   { echo -e "${RED}[✗]${RESET} $1"; exit 1; }

echo -e "${GREEN}"
echo "  ⬡ EXEFLOW — Installer"
echo "────────────────────────────────────"
echo -e "${RESET}"

# ── Root check
if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash install.sh"
fi

# ─────────────────────────────────────────────
#  PACKAGE MANAGER DETECTION
# ─────────────────────────────────────────────

detect_pkg_manager() {
    if   command -v apt-get &>/dev/null; then echo "apt"
    elif command -v pacman  &>/dev/null; then echo "pacman"
    elif command -v dnf     &>/dev/null; then echo "dnf"
    elif command -v zypper  &>/dev/null; then echo "zypper"
    elif command -v apk     &>/dev/null; then echo "apk"
    else echo "unknown"
    fi
}

# Install a package using the detected package manager
# Usage: pkg_install <pkg_apt> <pkg_pacman> <pkg_dnf> <pkg_zypper> <pkg_apk>
pkg_install() {
    local pkg_apt="$1"
    local pkg_pacman="$2"
    local pkg_dnf="$3"
    local pkg_zypper="$4"
    local pkg_apk="$5"

    case "$PKG_MANAGER" in
        apt)     apt-get install -y "$pkg_apt"    ;;
        pacman)  pacman -S --noconfirm "$pkg_pacman" ;;
        dnf)     dnf install -y "$pkg_dnf"        ;;
        zypper)  zypper install -y "$pkg_zypper"  ;;
        apk)     apk add --no-cache "$pkg_apk"    ;;
        *)       err "Unsupported package manager. Install manually: $pkg_apt / $pkg_pacman / $pkg_dnf" ;;
    esac
}

PKG_MANAGER=$(detect_pkg_manager)
ok "Package manager detected: ${PKG_MANAGER}"

# ─────────────────────────────────────────────
#  DEPENDENCY: python3
# ─────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
    info "python3 not found — installing..."
    pkg_install "python3" "python" "python3" "python3" "python3"
    ok "python3 installed"
else
    ok "python3 already present"
fi

# ─────────────────────────────────────────────
#  DEPENDENCY: python3-tk
# ─────────────────────────────────────────────

if ! python3 -c "import tkinter" 2>/dev/null; then
    info "python3-tk not found — installing..."
    pkg_install \
        "python3-tk" \
        "tk" \
        "python3-tkinter" \
        "python3-tk" \
        "python3-tkinter"
    ok "python3-tk installed"
else
    ok "python3-tk already present"
fi

# ─────────────────────────────────────────────
#  DEPENDENCY: curl or wget
# ─────────────────────────────────────────────

if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
    info "curl not found — installing..."
    pkg_install "curl" "curl" "curl" "curl" "curl"
    ok "curl installed"
else
    ok "curl/wget already present"
fi

# ─────────────────────────────────────────────
#  INSTALL EXEFLOW
# ─────────────────────────────────────────────

info "Creating ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
ok "Directory ready: ${INSTALL_DIR}"

info "Downloading exeflow.py..."
if command -v curl &>/dev/null; then
    curl -fsSL "${EXEFLOW_URL}" -o "${INSTALL_DIR}/exeflow.py" \
        || err "Download failed. Check the URL or your connection."
else
    wget -q "${EXEFLOW_URL}" -O "${INSTALL_DIR}/exeflow.py" \
        || err "Download failed. Check the URL or your connection."
fi
chmod 644 "${INSTALL_DIR}/exeflow.py"
ok "Downloaded to ${INSTALL_DIR}/exeflow.py"

# ─────────────────────────────────────────────
#  LAUNCHER
# ─────────────────────────────────────────────

info "Installing launcher at ${BIN_LINK}..."
cat > "${BIN_LINK}" << 'EOF'
#!/usr/bin/env bash
# ExeFlow launcher — runs detached, returns shell immediately
if [[ -z "$DISPLAY" && -z "$WAYLAND_DISPLAY" ]]; then
    echo "[exeflow] No display detected. Make sure you are in a graphical session."
    exit 1
fi
nohup python3 /opt/exeflow/exeflow.py "$@" > /tmp/exeflow.log 2>&1 &
disown
echo "[exeflow] Started (PID $!). Logs: /tmp/exeflow.log"
EOF

chmod 755 "${BIN_LINK}"
ok "Launcher installed: ${BIN_LINK}"

# ─────────────────────────────────────────────
#  DONE
# ─────────────────────────────────────────────

echo ""
echo -e "${GREEN}────────────────────────────────────${RESET}"
ok "ExeFlow installed successfully."
echo ""
echo "  Launch with:  exeflow"
echo "  Logs at:      /tmp/exeflow.log"
echo "  Script at:    ${INSTALL_DIR}/exeflow.py"
echo ""
