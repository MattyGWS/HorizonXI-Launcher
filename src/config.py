import os
import shutil
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

# Proton runner location:
# - Native/dev keeps the managed Proton install inside launcher data.
# - Flatpak uses Steam's standard host-visible compatibilitytools.d path.
#
# UMU/pressure-vessel expects Steam-runtime-style host paths. Keeping Proton
# fully inside the Flatpak app-data sandbox can make pressure-vessel fail while
# creating its nested runtime. The launcher still keeps the Wine prefix and game
# files in DATA_DIR; only the Proton runner is placed in the common host path.
STEAM_COMPATTOOLS_DIR = Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d"
PROTON_INSTALL_ROOT = STEAM_COMPATTOOLS_DIR if IS_FLATPAK else PROTON_DIR

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

# UMU launcher:
# - Native/dev uses the project copy.
# - Flatpak copies the bundled /app/bin/umu-run to ~/.local/bin/umu-run and runs
#   the writable host-visible copy. This avoids trying to execute/modify UMU
#   from the immutable /app tree and better matches a normal host UMU install.
BUNDLED_UMU_RUN = Path("/app/bin/umu-run")
HOST_LOCAL_BIN = Path.home() / ".local" / "bin"
HOST_UMU_RUN = HOST_LOCAL_BIN / "umu-run"
UMU_RUN = HOST_UMU_RUN if IS_FLATPAK else PROJECT_ROOT / "bin" / "umu-run"

ARIA2C = Path("/app/bin/aria2c") if IS_FLATPAK else Path(os.environ.get("ARIA2C", "aria2c"))


def ensure_umu_run_available() -> Path:
    """Ensure the configured umu-run path exists and is executable.

    In Flatpak, /app is read-only at runtime, so we never chmod or modify
    /app/bin/umu-run directly. Instead, we copy it once to ~/.local/bin/umu-run
    and use that host-visible copy for all launches.
    """
    if IS_FLATPAK:
        HOST_LOCAL_BIN.mkdir(parents=True, exist_ok=True)

        if not UMU_RUN.exists():
            if not BUNDLED_UMU_RUN.exists():
                raise FileNotFoundError(f"Bundled umu-run not found: {BUNDLED_UMU_RUN}")
            shutil.copy2(BUNDLED_UMU_RUN, UMU_RUN)

        UMU_RUN.chmod(UMU_RUN.stat().st_mode | 0o111)
        return UMU_RUN

    if UMU_RUN.exists():
        UMU_RUN.chmod(UMU_RUN.stat().st_mode | 0o111)

    return UMU_RUN


# HorizonXI game install
HORIZON_INSTALL_DIR = PREFIX_DIR / "drive_c" / "Program Files" / "HorizonXI"
GAME_DIR = HORIZON_INSTALL_DIR / "Game"
DOWNLOADS_DIR = HORIZON_INSTALL_DIR / "Downloads"

HORIZON_LOADER_EXE = GAME_DIR / "bootloader" / "horizon-loader.exe"
ASHITA_CLI_EXE = GAME_DIR / "Ashita-cli.exe"
ASHITA_BOOT_CONFIG = GAME_DIR / "config" / "boot" / "ashita.ini"

HORIZON_SERVER = "play.horizonxi.com"
