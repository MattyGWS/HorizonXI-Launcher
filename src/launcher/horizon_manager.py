import json
import urllib.request
import zipfile

from config import APP_DOWNLOADS_DIR, HORIZON_LAUNCHER_EXE, LAUNCHER_DIR


class HorizonManager:
    RELEASES_API_URL = "https://api.github.com/repos/HorizonFFXI/HorizonXI-Launcher-Binaries/releases/latest"

    def __init__(self):
        self.launcher_dir = LAUNCHER_DIR
        self.downloads_dir = APP_DOWNLOADS_DIR
        self.launcher_exe = HORIZON_LAUNCHER_EXE
        self.archive_path = self.downloads_dir / "HorizonXI-Launcher.nupkg"

    def ensure_dirs(self):
        self.launcher_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def is_installed(self):
        return self.launcher_exe.exists()

    def get_launcher_path(self):
        return str(self.launcher_exe)

    def get_latest_download_url(self):
        with urllib.request.urlopen(self.RELEASES_API_URL) as response:
            data = json.loads(response.read().decode("utf-8"))

        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".nupkg") and "full" in name.lower():
                return asset["browser_download_url"]

        raise RuntimeError("Could not find HorizonXI launcher .nupkg release asset.")

    def download(self, progress_callback=None):
        self.ensure_dirs()

        if self.archive_path.exists():
            if progress_callback:
                progress_callback("HorizonXI launcher archive already downloaded.", 1.0)
            else:
                print("HorizonXI launcher archive already downloaded.")
            return

        if progress_callback:
            progress_callback("Finding latest HorizonXI launcher release...", None)
        download_url = self.get_latest_download_url()

        if progress_callback:
            progress_callback("Downloading HorizonXI launcher...", 0.0)
        else:
            print("Downloading HorizonXI launcher...")
            print(download_url)

        def reporthook(block_count, block_size, total_size):
            if not progress_callback or total_size <= 0:
                return

            downloaded = min(block_count * block_size, total_size)
            fraction = downloaded / total_size
            percent = int(fraction * 100)
            progress_callback(f"Downloading HorizonXI launcher... {percent}%", fraction)

        urllib.request.urlretrieve(
            download_url,
            self.archive_path,
            reporthook=reporthook,
        )

        if progress_callback:
            progress_callback("HorizonXI launcher download complete.", 1.0)
        else:
            print("Download complete.")

    def extract(self, progress_callback=None):
        self.ensure_dirs()

        if self.is_installed():
            if progress_callback:
                progress_callback("HorizonXI launcher already installed.", 1.0)
            else:
                print("HorizonXI launcher already installed.")
            return

        if not self.archive_path.exists():
            raise FileNotFoundError(f"Missing archive: {self.archive_path}")

        if progress_callback:
            progress_callback("Extracting HorizonXI launcher...", None)
        else:
            print("Extracting HorizonXI launcher...")

        with zipfile.ZipFile(self.archive_path, "r") as archive:
            archive.extractall(self.launcher_dir)

        if progress_callback:
            progress_callback("HorizonXI launcher extraction complete.", 1.0)
        else:
            print("Extraction complete.")

    def install(self, progress_callback=None):
        if self.is_installed():
            if progress_callback:
                progress_callback("HorizonXI launcher already installed.", 1.0)
            else:
                print("HorizonXI launcher already installed.")
            return

        self.download(progress_callback)
        self.extract(progress_callback)

        if not self.is_installed():
            raise RuntimeError(
                f"HorizonXI launcher install failed. Expected: {self.launcher_exe}"
            )

        if progress_callback:
            progress_callback("HorizonXI launcher installed successfully.", 1.0)
        else:
            print("HorizonXI launcher installed successfully.")
