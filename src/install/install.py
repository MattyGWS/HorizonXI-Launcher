import shutil
from pathlib import Path

from config import APP_DOWNLOADS_DIR, DATA_DIR, DOWNLOADS_DIR, LAUNCHER_DIR, LOG_DIR, PREFIX_DIR, PROTON_DIR
from game.game_installer import GameInstallManager
from launcher.horizon_manager import HorizonManager
from proton.proton_manager import ProtonManager


class InstallManager:
    def __init__(self, proton: ProtonManager, horizon: HorizonManager):
        self.proton = proton
        self.horizon = horizon
        self.game = GameInstallManager()

    def is_proton_installed(self):
        return self.proton.is_installed()

    def is_official_launcher_installed(self):
        return self.horizon.is_installed()

    def is_game_installed(self):
        return self.game.is_installed()

    def get_game_status_text(self):
        return self.game.get_status_text()

    def check_game_update_available(self):
        return self.game.check_update_available()

    def is_installed(self):
        return (
            self.is_proton_installed()
            and self.is_official_launcher_installed()
            and self.is_game_installed()
        )

    def install(self, progress_callback=None):
        """Install/repair all managed runtime components.

        This installs Proton, keeps the official Horizon launcher available as an
        optional settings/troubleshooting tool, then installs the HorizonXI game
        files natively using our own downloader/extractor.
        """

        def progress(message, fraction=None):
            if progress_callback:
                progress_callback(message, fraction)
            else:
                print(message)

        def stage_progress(stage_start, stage_end):
            def callback(message, fraction=None):
                if fraction is None:
                    progress(message, None)
                    return

                overall_fraction = stage_start + ((stage_end - stage_start) * fraction)
                progress(message, overall_fraction)

            return callback

        progress("Checking Proton...", 0.0)

        if not self.proton.is_installed():
            progress("Installing GE-Proton7-42...", 0.02)
            self.proton.install(stage_progress(0.02, 0.18))
        else:
            progress("GE-Proton7-42 already installed.", 0.18)

        progress("Checking official HorizonXI launcher...", 0.19)

        if not self.horizon.is_installed():
            progress("Installing official HorizonXI launcher...", 0.20)
            self.horizon.install(stage_progress(0.20, 0.30))
        else:
            progress("Official HorizonXI launcher already installed.", 0.30)

        progress("Checking HorizonXI game files and updates...", 0.31)

        if not self.game.is_installed():
            progress("Installing HorizonXI game files...", 0.32)
        else:
            progress("Checking for HorizonXI game updates...", 0.32)

        was_game_installed = self.game.is_installed()
        self.game.install(stage_progress(0.32, 0.90))

        if self.game.is_installed():
            self.game.save_default_configuration_snapshot(overwrite=not was_game_installed)

        # Always run the silent prefix setup step when game files exist. This
        # makes Install / Repair fix an already-extracted game whose prefix is
        # missing the Microsoft VC++ runtime.
        if self.game.is_installed():
            progress("Preparing Wine prefix for HorizonXI...", 0.90)
            self.game.run_post_install_helpers(
                self.proton.get_path(),
                stage_progress(0.90, 1.00),
            )

        progress("Install complete.", 1.0)

    def install_game(self, progress_callback=None):
        """Install the game flow from the main stateful button.

        Proton is still required for launch, and the official launcher is still
        useful for settings, so this delegates to install() for now.
        """
        self.install(progress_callback)

    def nuclear_reset(self, progress_callback=None):
        """Remove all launcher-managed runtime data without deleting this app/project."""

        def progress(message, fraction=None):
            if progress_callback:
                progress_callback(message, fraction)
            else:
                print(message)

        managed_paths = [
            (PREFIX_DIR, "Wine prefix and HorizonXI game files"),
            (LAUNCHER_DIR, "official HorizonXI launcher files"),
            (PROTON_DIR, "managed Proton files"),
            (DOWNLOADS_DIR, "HorizonXI game download cache"),
            (APP_DOWNLOADS_DIR, "runtime download cache"),
            (LOG_DIR, "launcher logs"),
        ]

        total = len(managed_paths)
        progress("Starting nuclear reset...", 0.0)

        for index, (path, description) in enumerate(managed_paths, start=1):
            path = Path(path)
            progress(f"Removing {description}...", (index - 1) / total)

            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()

            progress(f"Removed {description}.", index / total)

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        progress("Nuclear reset complete.", 1.0)
