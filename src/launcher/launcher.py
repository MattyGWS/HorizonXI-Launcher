import os
import subprocess

from config import (
    PREFIX_DIR,
    UMU_RUN,
    GAME_DIR,
    ASHITA_CLI_EXE,
    ASHITA_BOOT_CONFIG,
    HORIZON_SERVER,
)
from launcher.horizon_manager import HorizonManager
from proton.proton_manager import ProtonManager


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

        subprocess.Popen(
            [str(UMU_RUN), self.horizon.get_launcher_path()],
            env=self._build_env(),
        )

    def launch_game_direct(self, username: str, password: str):
        self._ensure_umu_executable()
        if not ASHITA_CLI_EXE.exists():
            raise RuntimeError("Ashita-cli.exe not found.")

        if not ASHITA_BOOT_CONFIG.exists():
            raise RuntimeError("Ashita boot config not found.")

        self._update_ashita_boot_command(username, password)

        env = self._build_env()

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
        print("========================================")
        print()

        subprocess.Popen(
            [
                str(UMU_RUN),
                "./Ashita-cli.exe",
                "ashita.ini",
            ],
            cwd=str(GAME_DIR),
            env=env,
        )

    def _ensure_umu_executable(self):
        if UMU_RUN.exists():
            UMU_RUN.chmod(UMU_RUN.stat().st_mode | 0o111)

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
