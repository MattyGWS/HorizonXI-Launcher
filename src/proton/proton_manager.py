import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from config import (
    APP_DOWNLOADS_DIR,
    GE_PROTON_ARCHIVE,
    GE_PROTON_URL,
    GE_PROTON_VERSION,
    PREFIX_DIR,
    PROTON_INSTALL_ROOT,
    IS_FLATPAK,
)


class ProtonManager:
    VERSION = GE_PROTON_VERSION

    # Experimental Performance Mode uses a fixed Proton-GE build so we do not
    # depend on "latest" release asset ordering or architecture guessing.
    EXPERIMENTAL_BASE_VERSION = "GE-Proton10-34"
    EXPERIMENTAL_VERSION = f"{EXPERIMENTAL_BASE_VERSION}-HorizonExperimental"
    EXPERIMENTAL_ARCHIVE = f"{EXPERIMENTAL_BASE_VERSION}.tar.gz"
    EXPERIMENTAL_URL = (
        "https://github.com/GloriousEggroll/proton-ge-custom/releases/download/"
        f"{EXPERIMENTAL_BASE_VERSION}/{EXPERIMENTAL_ARCHIVE}"
    )
    EXPERIMENTAL_METADATA_FILENAME = "ge-proton-experimental-release.json"

    def __init__(self):
        self.proton_dir = PROTON_INSTALL_ROOT
        self.downloads_dir = APP_DOWNLOADS_DIR
        self.archive_path = self.downloads_dir / GE_PROTON_ARCHIVE
        self.proton_path = self.proton_dir / self.VERSION

        self.experimental_archive_path = self.downloads_dir / self.EXPERIMENTAL_ARCHIVE
        self.experimental_proton_path = self.proton_dir / self.EXPERIMENTAL_VERSION
        self.experimental_metadata_path = self.experimental_proton_path / self.EXPERIMENTAL_METADATA_FILENAME

    def ensure_dirs(self):
        self.proton_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def is_installed(self):
        proton_binary = self.proton_path / "proton"
        return self.proton_path.exists() and proton_binary.exists()

    def get_path(self):
        return str(self.proton_path)

    def is_experimental_installed(self):
        proton_binary = self.experimental_proton_path / "proton"
        return self.experimental_proton_path.exists() and proton_binary.exists()

    def get_experimental_path(self):
        return str(self.experimental_proton_path)

    def get_experimental_status_text(self):
        if not self.is_experimental_installed():
            return "Missing"

        metadata = self._read_experimental_metadata()
        version = metadata.get("version") or metadata.get("base_version")
        if version:
            return f"Installed ({version})"

        return f"Installed ({self.EXPERIMENTAL_BASE_VERSION})"

    def download(self, progress_callback=None):
        self.ensure_dirs()

        if self.archive_path.exists():
            if progress_callback:
                progress_callback(f"{self.VERSION} archive already downloaded.", 1.0)
            else:
                print("Proton archive already downloaded.")
            return

        if progress_callback:
            progress_callback(f"Downloading {self.VERSION}...", 0.0)
        else:
            print(f"Downloading {self.VERSION}...")
            print(GE_PROTON_URL)

        def reporthook(block_count, block_size, total_size):
            if not progress_callback or total_size <= 0:
                return

            downloaded = min(block_count * block_size, total_size)
            fraction = downloaded / total_size
            percent = int(fraction * 100)
            progress_callback(f"Downloading {self.VERSION}... {percent}%", fraction)

        urllib.request.urlretrieve(
            GE_PROTON_URL,
            self.archive_path,
            reporthook=reporthook,
        )

        if progress_callback:
            progress_callback(f"{self.VERSION} download complete.", 1.0)
        else:
            print("Download complete.")

    def extract(self, progress_callback=None):
        self.ensure_dirs()

        if self.is_installed():
            if progress_callback:
                progress_callback("Proton already installed.", 1.0)
            else:
                print("Proton already installed.")
            return

        if not self.archive_path.exists():
            raise FileNotFoundError(f"Missing archive: {self.archive_path}")

        if progress_callback:
            progress_callback(f"Extracting {self.VERSION}...", None)
        else:
            print(f"Extracting {self.archive_path}...")

        with tarfile.open(self.archive_path, "r:gz") as tar:
            tar.extractall(self.proton_dir)

        if progress_callback:
            progress_callback(f"{self.VERSION} extraction complete.", 1.0)
        else:
            print("Extraction complete.")

    def install(self, progress_callback=None):
        self.ensure_dirs()

        if self.is_installed():
            if progress_callback:
                progress_callback(f"{self.VERSION} is already installed.", 1.0)
            else:
                print(f"{self.VERSION} is already installed.")
            return

        self.download(progress_callback)
        self.extract(progress_callback)

        if not self.is_installed():
            raise RuntimeError("Proton install failed.")

        if progress_callback:
            progress_callback(f"{self.VERSION} installed successfully.", 1.0)
        else:
            print(f"{self.VERSION} installed successfully.")

    def install_experimental(self, progress_callback=None, install_prefix_helpers=True):
        """Install/reinstall the fixed Proton-GE experimental runtime.

        The Proton install is required. Prefix helpers are best-effort, so users
        can still use the experimental runtime even when protontricks is missing.
        """
        self.ensure_dirs()
        warnings = []

        def progress(message, fraction=None):
            if progress_callback:
                progress_callback(message, fraction)
            else:
                print(message)

        self._remove_legacy_experimental_install(progress)

        if self.is_experimental_installed():
            progress(f"{self.EXPERIMENTAL_BASE_VERSION} experimental runtime is already installed.", 0.70)
        else:
            progress(f"Downloading {self.EXPERIMENTAL_BASE_VERSION}...", 0.05)
            self._download_file(
                self.EXPERIMENTAL_URL,
                self.experimental_archive_path,
                f"Downloading {self.EXPERIMENTAL_BASE_VERSION}",
                progress,
                0.05,
                0.60,
            )

            progress(f"Extracting {self.EXPERIMENTAL_BASE_VERSION}...", 0.60)
            self._extract_experimental_archive(progress)
            progress(f"{self.EXPERIMENTAL_BASE_VERSION} experimental runtime installed.", 0.78)

        if install_prefix_helpers:
            progress("Installing optional experimental prefix components with protontricks...", 0.80)
            try:
                self.install_experimental_prefix_helpers(
                    progress_callback=lambda message, fraction=None: progress(
                        message,
                        0.80 + ((fraction or 0.0) * 0.18),
                    )
                )
            except Exception as error:
                warning = f"Optional protontricks components failed: {error}"
                warnings.append(warning)
                print(warning)
                progress(f"{self.EXPERIMENTAL_BASE_VERSION} installed. Optional protontricks components failed.", 0.98)

        if warnings:
            progress("Experimental Performance Mode installed with warnings.", 1.0)
        else:
            progress("Experimental Performance Mode is installed.", 1.0)

        return {"warnings": warnings}

    def install_experimental_prefix_helpers(self, progress_callback=None):
        if not self.is_experimental_installed():
            raise RuntimeError(f"Install {self.EXPERIMENTAL_BASE_VERSION} before installing experimental prefix components.")

        protontricks = shutil.which("protontricks")
        if not protontricks:
            raise RuntimeError("protontricks is not installed on the host. Install protontricks to add optional font/gdiplus components.")

        if progress_callback:
            progress_callback("Running protontricks: allfonts corefonts gdiplus...", 0.0)

        env = os.environ.copy()
        env["WINEPREFIX"] = str(PREFIX_DIR)
        env["PROTONPATH"] = self.get_experimental_path()
        env["WINEDLLOVERRIDES"] = "d3d8=n,b"

        command = [protontricks, "-q", "allfonts", "corefonts", "gdiplus"]

        if IS_FLATPAK:
            command = [
                "flatpak-spawn",
                "--host",
                f"--env=WINEPREFIX={env['WINEPREFIX']}",
                f"--env=PROTONPATH={env['PROTONPATH']}",
                f"--env=WINEDLLOVERRIDES={env['WINEDLLOVERRIDES']}",
                "protontricks",
                "-q",
                "allfonts",
                "corefonts",
                "gdiplus",
            ]

        result = subprocess.run(
            command,
            env=env if not IS_FLATPAK else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

        if result.stdout:
            print(result.stdout)

        if result.returncode != 0:
            raise RuntimeError(
                "protontricks failed while installing allfonts/corefonts/gdiplus "
                f"with exit code {result.returncode}."
            )

        if progress_callback:
            progress_callback("Experimental prefix components installed.", 1.0)

    def _download_file(self, url, destination, label, progress, start, end):
        if destination.exists() and destination.stat().st_size > 0:
            progress(f"{destination.name} already downloaded.", end)
            return

        def reporthook(block_count, block_size, total_size):
            if total_size <= 0:
                return
            downloaded = min(block_count * block_size, total_size)
            fraction = downloaded / total_size
            percent = int(fraction * 100)
            overall = start + ((end - start) * fraction)
            progress(f"{label}... {percent}%", overall)

        urllib.request.urlretrieve(url, destination, reporthook=reporthook)

    def _extract_experimental_archive(self, progress):
        with tempfile.TemporaryDirectory(prefix="horizon-ge-proton-experimental-") as temp_name:
            temp_dir = Path(temp_name)
            with tarfile.open(self.experimental_archive_path, "r:*") as tar:
                tar.extractall(temp_dir)

            extracted_root = self._find_extracted_proton_root(temp_dir)

            if self.experimental_proton_path.exists():
                shutil.rmtree(self.experimental_proton_path)

            shutil.move(str(extracted_root), str(self.experimental_proton_path))

        self.experimental_metadata_path.write_text(
            json.dumps(
                {
                    "version": self.EXPERIMENTAL_BASE_VERSION,
                    "archive_name": self.EXPERIMENTAL_ARCHIVE,
                    "source_url": self.EXPERIMENTAL_URL,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _find_extracted_proton_root(self, temp_dir):
        candidates = []
        for path in temp_dir.rglob("proton"):
            if path.is_file():
                candidates.append(path.parent)

        if not candidates:
            raise RuntimeError(f"Extracted {self.EXPERIMENTAL_BASE_VERSION} archive did not contain a proton executable.")

        return sorted(candidates, key=lambda path: len(path.relative_to(temp_dir).parts))[0]

    def _remove_legacy_experimental_install(self, progress=None):
        legacy_name = "Proton-" + "CachyOS"
        legacy_path = self.proton_dir / legacy_name
        if legacy_path.exists():
            if progress:
                progress("Removing old experimental runtime...", 0.02)
            shutil.rmtree(legacy_path)

    def _read_experimental_metadata(self):
        try:
            if self.experimental_metadata_path.exists():
                data = json.loads(self.experimental_metadata_path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def remove(self):
        if self.proton_path.exists():
            shutil.rmtree(self.proton_path)
        if self.experimental_proton_path.exists():
            shutil.rmtree(self.experimental_proton_path)
        legacy_name = "Proton-" + "CachyOS"
        legacy_path = self.proton_dir / legacy_name
        if legacy_path.exists():
            shutil.rmtree(legacy_path)
