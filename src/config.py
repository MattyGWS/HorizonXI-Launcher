import os
from pathlib import Path

APP_ID = "io.github.mattyws.HorizonXILauncher"
APP_NAME = "HorizonXI-Launcher"


def _is_flatpak() -> bool:
    return Path("/.flatpak-info").exists() or bool(os.environ.get("FLATPAK_ID"))


IS_FLATPAK = _is_flatpak()

# Data directory:
# - Native/dev: ~/.local/share/HorizonXI-Launcher
# - Flatpak:   ~/.var/app/io.github.mattyws.HorizonXILauncher/data/HorizonXI-Launcher
xdg_data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
DATA_DIR = xdg_data_home / APP_NAME

PROTON_DIR = DATA_DIR / "proton"
PREFIX_DIR = DATA_DIR / "prefix"
LOG_DIR = DATA_DIR / "logs"
LAUNCHER_DIR = DATA_DIR / "launcher"
APP_DOWNLOADS_DIR = DATA_DIR / "Downloads"

# Proton
GE_PROTON_VERSION = "GE-Proton7-42"
GE_PROTON_ARCHIVE = f"{GE_PROTON_VERSION}.tar.gz"
GE_PROTON_URL = (
    "https://github.com/GloriousEggroll/proton-ge-custom/releases/download/"
    f"{GE_PROTON_VERSION}/{GE_PROTON_ARCHIVE}"
)

# HorizonXI official launcher
HORIZON_LAUNCHER_VERSION = "1.3.1"
HORIZON_LAUNCHER_ARCHIVE = (
    f"HorizonXI_Launcher-{HORIZON_LAUNCHER_VERSION}-full.nupkg"
)
HORIZON_LAUNCHER_URL = (
    "https://github.com/HorizonFFXI/HorizonXI-Launcher-Binaries/releases/download/"
    f"v{HORIZON_LAUNCHER_VERSION}/{HORIZON_LAUNCHER_ARCHIVE}"
)

HORIZON_LAUNCHER_EXE = (
    LAUNCHER_DIR / "lib" / "net45" / "HorizonXI-Launcher.exe"
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Inside Flatpak these helpers are installed to /app/bin.
UMU_RUN = Path("/app/bin/umu-run") if IS_FLATPAK else PROJECT_ROOT / "bin" / "umu-run"
ARIA2C = Path("/app/bin/aria2c") if IS_FLATPAK else Path(os.environ.get("ARIA2C", "aria2c"))

# HorizonXI game install
HORIZON_INSTALL_DIR = PREFIX_DIR / "drive_c" / "Program Files" / "HorizonXI"
GAME_DIR = HORIZON_INSTALL_DIR / "Game"
DOWNLOADS_DIR = HORIZON_INSTALL_DIR / "Downloads"

HORIZON_LOADER_EXE = GAME_DIR / "bootloader" / "horizon-loader.exe"
ASHITA_CLI_EXE = GAME_DIR / "Ashita-cli.exe"
ASHITA_BOOT_CONFIG = GAME_DIR / "config" / "boot" / "ashita.ini"

HORIZON_SERVER = "play.horizonxi.com"
