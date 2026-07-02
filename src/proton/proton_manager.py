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
    EXPERIMENTAL_VERSION = "Proton-CachyOS"
    EXPERIMENTAL_RELEASES_API_URL = "https://api.github.com/repos/CachyOS/proton-cachyos/releases/latest"
    EXPERIMENTAL_METADATA_FILENAME = "proton-cachyos-release.json"

    def __init__(self):
        self.proton_dir = PROTON_INSTALL_ROOT
        self.downloads_dir = APP_DOWNLOADS_DIR
        self.archive_path = self.downloads_dir / GE_PROTON_ARCHIVE
        self.proton_path = self.proton_dir / self.VERSION
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
        tag_name = metadata.get("tag_name")
        if tag_name:
            return f"Installed ({tag_name})"

        return "Installed"

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
        """Install/update the optional Proton-CachyOS runtime and prefix extras."""
        self.ensure_dirs()

        def progress(message, fraction=None):
            if progress_callback:
                progress_callback(message, fraction)
            else:
                print(message)

        progress("Finding latest Proton-CachyOS release...", None)
        release = self._fetch_latest_experimental_release()
        asset = self._select_experimental_asset(release)
        archive_name = asset["name"]
        archive_url = asset["browser_download_url"]
        archive_path = self.downloads_dir / archive_name

        current = self._read_experimental_metadata()
        current_asset = current.get("asset_name")
        current_tag = current.get("tag_name")
        latest_tag = release.get("tag_name")

        if self.is_experimental_installed() and current_asset == archive_name and current_tag == latest_tag:
            progress("Latest Proton-CachyOS is already installed.", 0.45)
        else:
            progress(f"Downloading Proton-CachyOS {latest_tag or ''}...", 0.05)
            self._download_file(archive_url, archive_path, "Downloading Proton-CachyOS", progress, 0.05, 0.55)

            progress("Extracting Proton-CachyOS...", 0.55)
            self._extract_experimental_archive(archive_path, release, asset, progress)
            progress("Proton-CachyOS installed.", 0.75)

        if install_prefix_helpers:
            progress("Installing experimental prefix components...", 0.76)
            self.install_experimental_prefix_helpers(progress_callback=lambda message, fraction=None: progress(message, 0.76 + ((fraction or 0.0) * 0.24)))

        progress("Experimental Performance Mode is installed.", 1.0)

    def install_experimental_prefix_helpers(self, progress_callback=None):
        if not self.is_experimental_installed():
            raise RuntimeError("Install Proton-CachyOS before installing experimental prefix components.")

        if progress_callback:
            progress_callback("Running winetricks: allfonts corefonts gdiplus...", 0.0)

        env = os.environ.copy()
        env["WINEPREFIX"] = str(PREFIX_DIR)
        env["PROTONPATH"] = self.get_experimental_path()
        env["WINEDLLOVERRIDES"] = "d3d8=n,b"

        command = ["winetricks", "-q", "allfonts", "corefonts", "gdiplus"]

        if IS_FLATPAK:
            command = [
                "flatpak-spawn",
                "--host",
                f"--env=WINEPREFIX={env['WINEPREFIX']}",
                f"--env=PROTONPATH={env['PROTONPATH']}",
                f"--env=WINEDLLOVERRIDES={env['WINEDLLOVERRIDES']}",
                "winetricks",
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

        # 0 = success. Some winetricks verbs can return 1 when already present,
        # but treating that as success can hide real failures, so keep it strict.
        if result.returncode != 0:
            raise RuntimeError(
                "winetricks failed while installing allfonts/corefonts/gdiplus "
                f"with exit code {result.returncode}. Make sure winetricks is installed on the host."
            )

        if progress_callback:
            progress_callback("Experimental prefix components installed.", 1.0)

    def _fetch_latest_experimental_release(self):
        request = urllib.request.Request(
            self.EXPERIMENTAL_RELEASES_API_URL,
            headers={"User-Agent": "HorizonXI-Linux-Launcher/0.3"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected Proton-CachyOS release response.")

        return payload

    def _select_experimental_asset(self, release):
        assets = release.get("assets", [])
        candidates = []

        for asset in assets:
            name = str(asset.get("name", ""))
            lower = name.lower()
            if not asset.get("browser_download_url"):
                continue
            if not lower.endswith((".tar.gz", ".tar.xz", ".tgz")):
                continue
            if "sha" in lower or "checksum" in lower or "debug" in lower:
                continue
            candidates.append(asset)

        if not candidates:
            raise RuntimeError("Could not find a Proton-CachyOS tar archive in the latest release.")

        def score(asset):
            lower = str(asset.get("name", "")).lower()
            value = 0
            if "steamrt3" in lower:
                value += 30
            if "sniper" in lower:
                value += 20
            if "proton-cachyos" in lower:
                value += 10
            if lower.endswith(".tar.xz"):
                value += 5
            return value

        return sorted(candidates, key=score, reverse=True)[0]

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

    def _extract_experimental_archive(self, archive_path, release, asset, progress):
        with tempfile.TemporaryDirectory(prefix="horizon-proton-cachyos-") as temp_name:
            temp_dir = Path(temp_name)
            with tarfile.open(archive_path, "r:*") as tar:
                tar.extractall(temp_dir)

            extracted_root = self._find_extracted_proton_root(temp_dir)

            if self.experimental_proton_path.exists():
                shutil.rmtree(self.experimental_proton_path)

            shutil.move(str(extracted_root), str(self.experimental_proton_path))

        self.experimental_metadata_path.write_text(
            json.dumps(
                {
                    "tag_name": release.get("tag_name"),
                    "asset_name": asset.get("name"),
                    "html_url": release.get("html_url"),
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
            raise RuntimeError("Extracted Proton-CachyOS archive did not contain a proton executable.")

        # Prefer the shallowest containing folder. That should be the compatibility
        # tool root rather than nested helper paths.
        return sorted(candidates, key=lambda path: len(path.relative_to(temp_dir).parts))[0]

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
