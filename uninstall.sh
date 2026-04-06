#!/usr/bin/env bash
# ─────────────────────────────────────────────
#  ExeFlow — Uninstaller
#  Removes ExeFlow files only, leaves dependencies untouched.
#  Usage: sudo bash uninstall.sh
# ─────────────────────────────────────────────

INSTALL_DIR="/opt/exeflow"
BIN_LINK="/usr/local/bin/exeflow"

GREEN="\033[0;32m"
CYAN="\033[0;36m"
RED="\033[0;31m"
GRAY="\033[0;37m"
RESET="\033[0m"

info() { echo -e "${CYAN}[*]${RESET} $1"; }
ok()   { echo -e "${GREEN}[✓]${RESET} $1"; }
skip() { echo -e "${GRAY}[-]${RESET} $1"; }
err()  { echo -e "${RED}[✗]${RESET} $1"; exit 1; }

echo -e "${GREEN}"
echo "  ⬡ EXEFLOW — Uninstaller"
echo "────────────────────────────────────"
echo -e "${RESET}"

# ── Root check
if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash uninstall.sh"
fi

# ── Remove /opt/exeflow/
if [[ -d "$INSTALL_DIR" ]]; then
    info "Removing ${INSTALL_DIR}..."
    rm -rf "$INSTALL_DIR"
    ok "Removed ${INSTALL_DIR}"
else
    skip "${INSTALL_DIR} not found — skipping"
fi

# ── Remove /usr/local/bin/exeflow
if [[ -f "$BIN_LINK" ]]; then
    info "Removing ${BIN_LINK}..."
    rm -f "$BIN_LINK"
    ok "Removed ${BIN_LINK}"
else
    skip "${BIN_LINK} not found — skipping"
fi

# ── Clean up log if present
if [[ -f "/tmp/exeflow.log" ]]; then
    rm -f /tmp/exeflow.log
    ok "Removed /tmp/exeflow.log"
fi

echo ""
echo -e "${GREEN}────────────────────────────────────${RESET}"
ok "ExeFlow uninstalled. Dependencies (python3, python3-tk) were left untouched."
echo ""
echo "  To reinstall: sudo bash install.sh"
echo ""
