#!/usr/bin/env bash
set -euo pipefail

APP_ID="io.github.mattyws.HorizonXILauncher"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BASE_DIR="$DATA_HOME/$APP_ID"
PREFIX_DIR="$BASE_DIR/prefix"
LAUNCHER_DIR="$BASE_DIR/launcher"
PROTON_DIR="$BASE_DIR/proton/GE-Proton7-42"
LOG_DIR="$BASE_DIR/logs"
LOG_FILE="$LOG_DIR/launch.log"

mkdir -p "$PREFIX_DIR" "$LAUNCHER_DIR" "$LOG_DIR"

EXE="$LAUNCHER_DIR/HorizonXI-Launcher.exe"

if ! command -v umu-run >/dev/null 2>&1; then
  echo "ERROR: umu-run was not found. Install umu-launcher first." | tee -a "$LOG_FILE"
  exit 127
fi

if [[ ! -f "$EXE" ]]; then
  echo "ERROR: HorizonXI-Launcher.exe was not found at:" | tee -a "$LOG_FILE"
  echo "  $EXE" | tee -a "$LOG_FILE"
  echo "Put the official HorizonXI launcher exe there for now." | tee -a "$LOG_FILE"
  exit 2
fi

# Prefer our managed GE-Proton7-42 if present. Otherwise allow PROTONPATH from the environment.
if [[ -d "$PROTON_DIR" ]]; then
  export PROTONPATH="$PROTON_DIR"
elif [[ -z "${PROTONPATH:-}" ]]; then
  echo "ERROR: GE-Proton7-42 not found at:" | tee -a "$LOG_FILE"
  echo "  $PROTON_DIR" | tee -a "$LOG_FILE"
  echo "Either put GE-Proton7-42 there or run with PROTONPATH=/path/to/GE-Proton7-42." | tee -a "$LOG_FILE"
  exit 3
fi

export WINEPREFIX="$PREFIX_DIR"
export GAMEID="horizonxi"
export STORE="none"
export WINEDLLOVERRIDES="d3d8=n,b"
export DXVK_FRAME_RATE="60"

{
  echo "==== HorizonXI launch $(date -Is) ===="
  echo "WINEPREFIX=$WINEPREFIX"
  echo "PROTONPATH=$PROTONPATH"
  echo "EXE=$EXE"
  echo
} >> "$LOG_FILE"

exec umu-run "$EXE" "$@" 2>&1 | tee -a "$LOG_FILE"
