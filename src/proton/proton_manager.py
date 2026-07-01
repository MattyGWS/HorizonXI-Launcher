import shutil
import tarfile
import urllib.request
from pathlib import Path

from config import (
    APP_DOWNLOADS_DIR,
    GE_PROTON_ARCHIVE,
    GE_PROTON_URL,
    GE_PROTON_VERSION,
    PROTON_INSTALL_ROOT,
)


class ProtonManager:
    VERSION = GE_PROTON_VERSION

    def __init__(self):
        self.proton_dir = PROTON_INSTALL_ROOT
        self.downloads_dir = APP_DOWNLOADS_DIR
        self.archive_path = self.downloads_dir / GE_PROTON_ARCHIVE
        self.proton_path = self.proton_dir / self.VERSION

    def ensure_dirs(self):
        self.proton_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def is_installed(self):
        proton_binary = self.proton_path / "proton"
        return self.proton_path.exists() and proton_binary.exists()

    def get_path(self):
        return str(self.proton_path)

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

    def remove(self):
        if self.proton_path.exists():
            shutil.rmtree(self.proton_path)
