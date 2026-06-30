import re
import shutil
import subprocess
import time
from pathlib import Path

from config import ARIA2C


class TorrentBackendUnavailable(RuntimeError):
    pass


_PROGRESS_PERCENT_RE = re.compile(r"\((\d+(?:\.\d+)?)%\)")
_SPEED_RE = re.compile(r"DL:([^\]\s]+)")
_PEERS_RE = re.compile(r"CN:(\d+)")
_ETA_RE = re.compile(r"ETA:([^\]\s]+)")


class TorrentDownloader:
    """Torrent/magnet downloader.

    Prefer aria2c because it is easy to bundle in the Flatpak and does not need
    Python binary bindings. Keep a libtorrent fallback for developer machines
    where aria2c is not installed but rb_libtorrent-python3 is available.
    """

    def __init__(self, download_dir: Path):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _aria2_command(self):
        configured = str(ARIA2C)
        if "/" in configured:
            if Path(configured).exists():
                return configured
            return None
        return shutil.which(configured)

    def download(self, magnet: str, expected_filename: str, progress_callback=None) -> Path:
        destination = self.download_dir / expected_filename
        if destination.exists() and destination.stat().st_size > 0:
            if progress_callback:
                progress_callback(f"{expected_filename} already downloaded.", 1.0)
            return destination

        aria2c = self._aria2_command()
        if aria2c:
            return self._download_with_aria2c(
                aria2c,
                magnet,
                expected_filename,
                progress_callback,
            )

        # Development fallback only. The Flatpak should bundle aria2c.
        return self._download_with_libtorrent_fallback(
            magnet,
            expected_filename,
            progress_callback,
        )

    def _download_with_aria2c(
        self,
        aria2c: str,
        magnet: str,
        expected_filename: str,
        progress_callback=None,
    ) -> Path:
        destination = self.download_dir / expected_filename

        if progress_callback:
            progress_callback(f"Preparing aria2 download for {expected_filename}...", None)

        cmd = [
            aria2c,
            "--dir", str(self.download_dir),
            "--seed-time=0",
            "--follow-torrent=mem",
            "--bt-enable-lpd=true",
            "--enable-dht=true",
            "--enable-peer-exchange=true",
            "--summary-interval=1",
            "--console-log-level=notice",
            "--download-result=hide",
            "--file-allocation=none",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            magnet,
        ]

        process = subprocess.Popen(
            cmd,
            cwd=str(self.download_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        last_percent = -1
        last_message = ""

        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                # aria2 uses carriage returns for progress updates.
                for chunk in raw_line.replace("\r", "\n").splitlines():
                    line = chunk.strip()
                    if not line:
                        continue

                    percent_match = _PROGRESS_PERCENT_RE.search(line)
                    if percent_match:
                        fraction = max(0.0, min(1.0, float(percent_match.group(1)) / 100.0))
                        percent = int(fraction * 100)
                        speed = _first_match(_SPEED_RE, line)
                        peers = _first_match(_PEERS_RE, line)
                        eta = _first_match(_ETA_RE, line)

                        bits = [f"Downloading {expected_filename}... {percent}%"]
                        extra = []
                        if speed:
                            extra.append(speed)
                        if peers:
                            extra.append(f"{peers} peers")
                        if eta:
                            extra.append(f"ETA {eta}")
                        if extra:
                            bits.append(f"({', '.join(extra)})")
                        message = " ".join(bits)

                        if progress_callback and (percent != last_percent or message != last_message):
                            progress_callback(message, fraction)
                            last_percent = percent
                            last_message = message
                    elif "download completed" in line.lower() and progress_callback:
                        progress_callback(f"{expected_filename} download complete.", 1.0)
                    elif progress_callback and (
                        "metadata" in line.lower()
                        or "dht" in line.lower()
                        or "peer" in line.lower()
                    ):
                        # Useful during the magnet metadata phase, before percent exists.
                        progress_callback(f"Finding peers for {expected_filename}...", None)

            return_code = process.wait()
        finally:
            if process.poll() is None:
                process.kill()

        if return_code != 0:
            raise RuntimeError(f"aria2c failed for {expected_filename} with exit code {return_code}.")

        # Give the disk a moment to flush file metadata.
        time.sleep(0.5)

        if not destination.exists():
            matches = list(self.download_dir.glob(expected_filename))
            if matches:
                destination = matches[0]

        if not destination.exists():
            raise FileNotFoundError(
                f"aria2c finished but {expected_filename} was not found in {self.download_dir}."
            )

        if progress_callback:
            progress_callback(f"{expected_filename} download complete.", 1.0)

        return destination

    def _download_with_libtorrent_fallback(self, magnet: str, expected_filename: str, progress_callback=None) -> Path:
        try:
            import libtorrent as lt  # type: ignore
        except Exception as error:
            raise TorrentBackendUnavailable(
                "Torrent backend is unavailable. Install aria2 for development, "
                "or use the Flatpak build which bundles aria2c. Fedora package: aria2. "
                "Fallback rb_libtorrent-python3 is also supported for development."
            ) from error

        destination = self.download_dir / expected_filename
        if progress_callback:
            progress_callback(f"Preparing torrent for {expected_filename}...", None)

        session = lt.session()
        try:
            session.apply_settings({
                "listen_interfaces": "0.0.0.0:6881,[::]:6881",
                "enable_dht": True,
                "enable_lsd": True,
                "enable_upnp": True,
                "enable_natpmp": True,
                "user_agent": "HorizonXI-Linux-Launcher/0.1 libtorrent",
            })
        except Exception:
            pass

        params = {
            "save_path": str(self.download_dir),
            "storage_mode": lt.storage_mode_t.storage_mode_sparse,
        }
        handle = lt.add_magnet_uri(session, magnet, params)

        waited = 0
        while not handle.has_metadata():
            status = handle.status()
            if progress_callback:
                progress_callback(f"Finding peers for {expected_filename}... {status.num_peers} peers", None)
            time.sleep(1)
            waited += 1
            if waited > 600:
                raise TimeoutError(f"Timed out fetching torrent metadata for {expected_filename}.")

        last_percent = -1
        while True:
            status = handle.status()
            fraction = max(0.0, min(1.0, float(status.progress)))
            percent = int(fraction * 100)
            if progress_callback and percent != last_percent:
                progress_callback(
                    f"Downloading {expected_filename}... {percent}% "
                    f"({status.download_rate / (1024 * 1024):.1f} MiB/s, {status.num_peers} peers)",
                    fraction,
                )
                last_percent = percent
            if status.is_seeding or fraction >= 1.0:
                break
            time.sleep(1)

        time.sleep(0.5)
        if not destination.exists():
            raise FileNotFoundError(f"Torrent finished but {expected_filename} was not found.")
        if progress_callback:
            progress_callback(f"{expected_filename} download complete.", 1.0)
        return destination


def _first_match(pattern, text):
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1)
