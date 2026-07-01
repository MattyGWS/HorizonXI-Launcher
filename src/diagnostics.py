import platform
import shutil
import urllib.request
from pathlib import Path

from config import ARIA2C, BUNDLED_UMU_RUN, DATA_DIR, IS_FLATPAK, PROJECT_ROOT, PROTON_INSTALL_ROOT, UMU_RUN, ensure_umu_run_available


def _exists_command(path_or_command) -> bool:
    text = str(path_or_command)
    if "/" in text:
        return Path(text).exists()
    return shutil.which(text) is not None


def print_startup_diagnostics():
    print("========================================")
    print(" HorizonXI Launcher diagnostics")
    print("========================================")
    print(f"[diag] Python  {platform.python_version()}")
    print(f"[diag] System  {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"[diag] Project {PROJECT_ROOT}")
    print(f"[diag] Data    {DATA_DIR}")
    print(f"[diag] Flatpak {IS_FLATPAK}")
    print(f"[diag] Proton  {PROTON_INSTALL_ROOT}")

    try:
        import gi  # noqa: F401
        print("[diag] OK      PyGObject/gi import works")
    except Exception as error:
        print(f"[diag] MISSING PyGObject/gi import failed: {error}")

    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        print("[diag] OK      GTK4/libadwaita bindings import")
    except Exception as error:
        print(f"[diag] MISSING GTK4/libadwaita bindings failed: {error}")

    if _exists_command(ARIA2C):
        print(f"[diag] OK      aria2c found: {ARIA2C}")
    else:
        print(f"[diag] MISSING aria2c not found: {ARIA2C}. Install aria2 for dev or use the Flatpak.")

    # libtorrent is no longer required, but useful as a dev fallback.
    try:
        import libtorrent as lt  # type: ignore
        print(f"[diag] OK      libtorrent fallback import works: {lt.version}")
    except Exception as error:
        print(f"[diag] INFO    libtorrent fallback unavailable: {error}")

    if IS_FLATPAK:
        print(f"[diag] Bundled umu-run {BUNDLED_UMU_RUN}")

    try:
        ensure_umu_run_available()
        if UMU_RUN.exists():
            print(f"[diag] OK      umu-run ready: {UMU_RUN}")
        else:
            print(f"[diag] MISSING umu-run missing: {UMU_RUN}")
    except Exception as error:
        print(f"[diag] ERROR   umu-run setup failed: {error}")

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        test_file = DATA_DIR / ".write-test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        print("[diag] OK      data directory is writable")
    except Exception as error:
        print(f"[diag] ERROR   data directory is not writable: {error}")

    try:
        with urllib.request.urlopen("https://api.horizonxi.com/api/v1/launcher/latest-version", timeout=8) as response:
            print(f"[diag] OK      Horizon launcher API reachable (HTTP {response.status})")
    except Exception as error:
        print(f"[diag] WARN    Horizon launcher API check failed: {error}")

    print("========================================")
    print()
