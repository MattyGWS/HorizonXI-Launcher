import os
import subprocess

from config import (
    PREFIX_DIR,
    UMU_RUN,
    GAME_DIR,
    ASHITA_CLI_EXE,
    ASHITA_BOOT_CONFIG,
    HORIZON_SERVER,
    IS_FLATPAK,
    ensure_umu_run_available,
)
from launcher.horizon_manager import HorizonManager
from proton.proton_manager import ProtonManager


def _umu_command(args, env=None, cwd=None):
    """Build a UMU command.

    In Flatpak, run UMU on the host with flatpak-spawn so Proton can use the
    host Mesa/GL stack instead of being trapped inside the launcher sandbox.
    """
    args = [str(arg) for arg in args]

    if not IS_FLATPAK:
        return [str(UMU_RUN), *args]

    command = ["flatpak-spawn", "--host"]

    if cwd is not None:
        command.append(f"--directory={cwd}")

    for key in ("WINEPREFIX", "PROTONPATH", "WINEDLLOVERRIDES"):
        if env and key in env:
            command.append(f"--env={key}={env[key]}")

    command.extend([str(UMU_RUN), *args])
    return command


class Launcher:
    def __init__(self, proton: ProtonManager, horizon: HorizonManager):
        self.proton = proton
        self.horizon = horizon
        self.prefix_dir = PREFIX_DIR

    def can_launch(self):
        return self.proton.is_installed() and self.horizon.is_installed()

    def launch(self):
        self._ensure_umu_executable()
        if not self.can_launch():
            raise RuntimeError("Cannot launch: required components are missing.")

        self.prefix_dir.mkdir(parents=True, exist_ok=True)

        env = self._build_env()
        command = _umu_command(
            [self.horizon.get_launcher_path()],
            env=env,
        )

        subprocess.Popen(
            command,
            env=env if not IS_FLATPAK else None,
        )

    def launch_game_direct(self, username: str, password: str):
        self._ensure_umu_executable()
        if not ASHITA_CLI_EXE.exists():
            raise RuntimeError("Ashita-cli.exe not found.")

        if not ASHITA_BOOT_CONFIG.exists():
            raise RuntimeError("Ashita boot config not found.")

        self._update_ashita_boot_command(username, password)

        env = self._build_env()
        command = _umu_command(
            ["./Ashita-cli.exe", "ashita.ini"],
            env=env,
            cwd=GAME_DIR,
        )

        print()
        print("========================================")
        print(" HorizonXI Direct Launch")
        print("========================================")
        print("Working directory :", GAME_DIR)
        print("Executable        : ./Ashita-cli.exe")
        print("Config argument   : ashita.ini")
        print("Edited config     :", ASHITA_BOOT_CONFIG)
        print("WINEPREFIX        :", env["WINEPREFIX"])
        print("PROTONPATH        :", env["PROTONPATH"])
        print("Command           :", " ".join(command))
        print("========================================")
        print()

        subprocess.Popen(
            command,
            cwd=str(GAME_DIR) if not IS_FLATPAK else None,
            env=env if not IS_FLATPAK else None,
        )

    def _ensure_umu_executable(self):
        ensure_umu_run_available()

    def _build_env(self):
        env = os.environ.copy()
        env["WINEPREFIX"] = str(self.prefix_dir)
        env["PROTONPATH"] = self.proton.get_path()
        env["WINEDLLOVERRIDES"] = "d3d8=n,b"
        return env

    def _update_ashita_boot_command(self, username: str, password: str):
        command = (
            f"command = --server {HORIZON_SERVER} "
            f"--username {username} "
            f"--password {password}"
        )

        lines = ASHITA_BOOT_CONFIG.read_text(encoding="utf-8").splitlines()

        updated_lines = []
        replaced = False

        for line in lines:
            if line.strip().startswith("command ="):
                updated_lines.append(command)
                replaced = True
            else:
                updated_lines.append(line)

        if not replaced:
            raise RuntimeError("Could not find command line in ashita.ini.")

        ASHITA_BOOT_CONFIG.write_text(
            "\n".join(updated_lines) + "\n",
            encoding="utf-8",
        )
