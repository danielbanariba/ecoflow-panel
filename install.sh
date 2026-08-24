#!/usr/bin/env bash
#
# ecoflow-panel installer.
#
#   curl -fsSL https://raw.githubusercontent.com/danielbanariba/ecoflow-panel/main/install.sh | bash
#
# Installs the core client, detects the running desktop, and installs the panel
# frontend that fits it. Safe to re-run: every step is idempotent.
#
#   --uninstall     remove everything this installed
#   --no-watch      skip the power-outage timer
#   --frontend X    force kde | gnome | waybar | none
set -uo pipefail

REPO_RAW="https://raw.githubusercontent.com/danielbanariba/ecoflow-panel/main"
BIN="$HOME/.local/bin"
CONF="$HOME/.config/ecoflow"
UNITS="$HOME/.config/systemd/user"

c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
ok()   { printf '%s  ok  %s %s\n' "$c_ok"   "$c_off" "$*"; }
warn() { printf '%s warn %s %s\n' "$c_warn" "$c_off" "$*"; }
die()  { printf '%s fail %s %s\n' "$c_err"  "$c_off" "$*" >&2; exit 1; }
step() { printf '\n%s== %s ==%s\n' "$c_dim" "$*" "$c_off"; }

FRONTEND=""; WATCH=1; MODE=install
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) MODE=uninstall ;;
    --no-watch)  WATCH=0 ;;
    --frontend)  FRONTEND="${2:-}"; shift ;;
    -h|--help)   sed -n '2,14p' "$0"; exit 0 ;;
  esac
  shift
done

# ---------------------------------------------------------------- source files
# Works both from a clone and from `curl | bash`, where $0 is stdin and there is
# no repo on disk to copy from.
SRC=""
if [ -f "$(dirname "${BASH_SOURCE[0]}")/core/ecoflow-battery" ] 2>/dev/null; then
  SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

fetch() { # fetch <repo-relative-path> <destination>
  local rel="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -n "$SRC" ] && [ -f "$SRC/$rel" ]; then
    cp "$SRC/$rel" "$dest"
  else
    curl -fsSL "$REPO_RAW/$rel" -o "$dest" || return 1
  fi
}

# ------------------------------------------------------------------- uninstall
if [ "$MODE" = uninstall ]; then
  step "Removing"
  systemctl --user disable --now ecoflow-power-watch.timer 2>/dev/null && ok "timer stopped"
  rm -f "$UNITS/ecoflow-power-watch."{service,timer}
  systemctl --user daemon-reload 2>/dev/null
  rm -f "$BIN/ecoflow-battery" "$BIN/ecoflow-power-watch" "$BIN/ecoflow-waybar"
  rm -rf "$HOME/.local/share/plasma/plasmoids/local.ecoflow"
  rm -rf "$HOME/.local/share/gnome-shell/extensions/ecoflow@banariba.local"
  rm -f "$HOME/.cache/ecoflow-battery.json" "$HOME/.cache/ecoflow-power-watch.json"
  ok "binaries, units and frontends removed"
  warn "$CONF kept — it holds your API keys. Delete it yourself if you mean to."
  exit 0
fi

# ------------------------------------------------------------ preflight
step "Checking prerequisites"
command -v python3 >/dev/null || die "python3 is required"
ok "python3 $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:2])))')"
command -v curl >/dev/null || die "curl is required"
ok "curl"
command -v notify-send >/dev/null || warn "notify-send missing — desktop alerts will be silent"

# ------------------------------------------------------------ core
step "Installing the client"
mkdir -p "$BIN"
for f in ecoflow-battery ecoflow-power-watch; do
  fetch "core/$f" "$BIN/$f" || die "could not fetch core/$f"
  chmod 755 "$BIN/$f"
  ok "$BIN/$f"
done
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) warn "$BIN is not on PATH — add it to your shell profile" ;;
esac

# ------------------------------------------------------------ credentials
step "Credentials"
mkdir -p "$CONF"
if [ -s "$CONF/credentials" ] && grep -q '^ACCESS_KEY=.\+' "$CONF/credentials"; then
  ok "already present, left untouched"
else
  fetch "core/credentials.example" "$CONF/credentials" || die "could not fetch the template"
  chmod 600 "$CONF/credentials"
  warn "put your keys in $CONF/credentials, then re-run this installer"
  warn "keys come from https://developer.ecoflow.com -> Security Information Management"
  NEEDS_KEYS=1
fi

if [ -z "${NEEDS_KEYS:-}" ]; then
  if grep -q '^DEVICE_SN=.\+' "$CONF/credentials"; then
    ok "device serial already stored"
  else
    if "$BIN/ecoflow-battery" --discover >/dev/null 2>&1; then
      ok "device discovered and stored"
    else
      warn "could not reach the API — check the keys in $CONF/credentials"
    fi
  fi
fi

# ------------------------------------------------------------ frontend
step "Desktop frontend"
if [ -z "$FRONTEND" ]; then
  case "${XDG_CURRENT_DESKTOP:-}" in
    *KDE*)   FRONTEND=kde ;;
    *GNOME*) FRONTEND=gnome ;;
    *)       command -v waybar >/dev/null && FRONTEND=waybar || FRONTEND=none ;;
  esac
  ok "detected: ${XDG_CURRENT_DESKTOP:-unknown} -> $FRONTEND"
fi

case "$FRONTEND" in
  kde)
    D="$HOME/.local/share/plasma/plasmoids/local.ecoflow"
    for f in metadata.json contents/ui/main.qml; do
      fetch "kde/plasmoid/$f" "$D/$f" || die "could not fetch kde/plasmoid/$f"
    done
    ok "plasmoid installed"
    echo "     add it: right-click the panel -> Add Widgets -> EcoFlow Battery"
    ;;
  gnome)
    D="$HOME/.local/share/gnome-shell/extensions/ecoflow@banariba.local"
    for f in metadata.json extension.js stylesheet.css; do
      fetch "gnome/$f" "$D/$f" || die "could not fetch gnome/$f"
    done
    ok "extension installed"
    echo "     enable it: gnome-extensions enable ecoflow@banariba.local"
    echo "     Wayland needs a logout before a new extension can load."
    ;;
  waybar)
    fetch "waybar/ecoflow-waybar" "$BIN/ecoflow-waybar" && chmod 755 "$BIN/ecoflow-waybar"
    ok "waybar helper installed at $BIN/ecoflow-waybar"
    echo "     snippet to paste into your config: $(dirname "$0")/waybar/config.jsonc"
    ;;
  none)
    warn "no supported panel found — the CLI still works"
    ;;
esac

# ------------------------------------------------------------ outage watcher
if [ "$WATCH" = 1 ]; then
  step "Power-outage alerts"
  mkdir -p "$UNITS"
  for f in ecoflow-power-watch.service ecoflow-power-watch.timer; do
    fetch "systemd/$f" "$UNITS/$f" || die "could not fetch systemd/$f"
  done
  systemctl --user daemon-reload
  systemctl --user enable --now ecoflow-power-watch.timer >/dev/null 2>&1 \
    && ok "timer enabled, checking every minute" \
    || warn "could not enable the timer"
fi

# ------------------------------------------------------------ done
step "Done"
if [ -n "${NEEDS_KEYS:-}" ]; then
  echo "  Next: put your keys in $CONF/credentials and run this again."
else
  printf '  Reading right now: '
  "$BIN/ecoflow-battery" 2>/dev/null || echo "(no reading — check the keys)"
fi
echo
echo "  ecoflow-battery              current charge"
echo "  ecoflow-battery --json       all 242 fields"
echo "  ecoflow-power-watch --status mains present or not"
# Piped from curl, $0 is "bash", so print the command that actually works.
if [ -n "$SRC" ]; then
  echo "  $0 --uninstall               remove everything"
else
  echo "  curl -fsSL $REPO_RAW/install.sh | bash -s -- --uninstall"
  echo "                               remove everything"
fi
