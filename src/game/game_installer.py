import json
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from config import ASHITA_BOOT_CONFIG, ASHITA_CLI_EXE, DOWNLOADS_DIR, GAME_DIR, PREFIX_DIR, UMU_RUN, IS_FLATPAK, ensure_umu_run_available
from game.manifest import INSTALL_GAME_URL, LATEST_VERSION_URL, PREREQS_ARCHIVE, UPDATE_GAME_URL
from game.torrent_downloader import TorrentDownloader
from addons.addon_manager import AddonManager
from addons.plugin_manager import PluginManager


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


class GameInstallManager:
    """Installs and updates HorizonXI game files.

    The official HorizonXI launcher obtains the current base game and patch
    magnets from the public launcher API. This class mirrors that behaviour:

      fresh install:
        GET /api/v1/launcher/install-game

      existing install:
        GET /api/v1/launcher/latest-version
        GET /api/v1/launcher/update-game?ver=<installedVersion>
    """

    MARKER_FILENAME = "linux-launcher-install.json"

    def __init__(self):
        self.downloads_dir = DOWNLOADS_DIR
        self.game_dir = GAME_DIR
        self.prereqs_dir = DOWNLOADS_DIR / "Prereqs"
        self.marker_path = self.game_dir / self.MARKER_FILENAME
        self.torrent_downloader = TorrentDownloader(self.downloads_dir)

    def ensure_dirs(self):
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.game_dir.mkdir(parents=True, exist_ok=True)

    def is_installed(self):
        required_paths = [
            ASHITA_CLI_EXE,
            ASHITA_BOOT_CONFIG,
            self.game_dir / "version.json",
            self.game_dir
            / "SquareEnix"
            / "PlayOnlineViewer"
            / "viewer"
            / "com"
            / "polcore.dll",
        ]
        return all(path.exists() for path in required_paths)

    def get_version(self):
        """Return the installed numeric game version if known."""
        marker = self._read_marker()
        version = marker.get("installedVersion") or marker.get("latestVersion")
        if version is not None:
            return version

        version_file = self.game_dir / "version.json"
        if not version_file.exists():
            return None

        try:
            data = json.loads(version_file.read_text(encoding="utf-8"))
        except Exception:
            return None

        if isinstance(data, dict):
            return (
                data.get("version")
                or data.get("currentVersion")
                or data.get("gameVersion")
                or data.get("latestVersion")
            )

        if isinstance(data, int):
            return data

        if isinstance(data, str) and data.isdigit():
            return int(data)

        return None

    def get_marketing_version(self):
        marker = self._read_marker()
        return (
            marker.get("installedMarketingVersion")
            or marker.get("latestMarketingVersion")
            or marker.get("baseGameMarketingVersion")
        )

    def get_status_text(self):
        if not self.is_installed():
            return "Missing"

        marketing_version = self.get_marketing_version()
        numeric_version = self.get_version()

        if marketing_version:
            return f"Version {marketing_version} installed"

        if numeric_version is not None:
            return f"Version {numeric_version} installed"

        return "Installed"

    def install(self, progress_callback=None):
        """Install if missing, otherwise update if the API reports patches."""
        if self.is_installed():
            return self.update(progress_callback)

        return self.install_fresh(progress_callback)

    def install_fresh(self, progress_callback=None):
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
                overall = stage_start + ((stage_end - stage_start) * fraction)
                progress(message, overall)

            return callback

        self.ensure_dirs()

        progress("Fetching HorizonXI install manifest...", 0.0)
        manifest = self.fetch_install_manifest()
        archives = self.build_fresh_install_plan(manifest)

        if not archives:
            raise RuntimeError("HorizonXI install API returned no game archives.")

        prereqs_zip = self.download_prereqs(stage_progress(0.00, 0.04))
        self.extract_prereqs(prereqs_zip, stage_progress(0.04, 0.06))

        archive_count = len(archives)
        archive_span = 0.94 / archive_count
        base_start = 0.06

        for index, archive in enumerate(archives):
            archive_start = base_start + (archive_span * index)
            download_start = archive_start
            extract_start = archive_start + (archive_span * 0.72)
            archive_end = archive_start + archive_span

            archive_path = self.download_game_archive(
                archive,
                stage_progress(download_start, extract_start),
            )
            self.apply_delete_files(archive)
            self.extract_game_archive(
                archive_path,
                stage_progress(extract_start, archive_end),
            )

        self._write_linux_installer_marker(
            manifest=manifest,
            archives=archives,
            install_type="fresh",
        )

        if not self.is_installed():
            raise RuntimeError(
                "Game install finished, but required files were not found. "
                "Try Repair Installation or inspect the extracted Game folder."
            )

        progress("HorizonXI game install complete.", 1.0)

    def update(self, progress_callback=None):
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
                overall = stage_start + ((stage_end - stage_start) * fraction)
                progress(message, overall)

            return callback

        if not self.is_installed():
            return self.install_fresh(progress_callback)

        current_version = self.get_version()
        if current_version is None:
            progress("Installed game version is unknown; fetching install manifest...", 0.0)
            install_manifest = self.fetch_install_manifest()
            latest_version = install_manifest.get("latestVersion")
            self._write_linux_installer_marker(
                manifest=install_manifest,
                archives=[],
                install_type="adopt-existing",
                installed_version=latest_version,
            )
            progress("Existing install adopted.", 1.0)
            return

        progress("Checking HorizonXI game version...", 0.0)
        latest_version = self.fetch_latest_version()

        try:
            current_int = int(current_version)
            latest_int = int(latest_version)
        except Exception:
            progress("Could not compare installed/latest versions; skipping update.", 1.0)
            return

        if current_int >= latest_int:
            progress("HorizonXI game is already up to date.", 1.0)
            return

        progress(f"Updating HorizonXI game from version {current_int} to {latest_int}...", 0.05)
        update_manifest = self.fetch_update_manifest(current_int)
        patches = self.build_update_plan(update_manifest)

        if not patches:
            self._write_linux_installer_marker(
                manifest={"latestVersion": latest_int, "updateData": []},
                archives=[],
                install_type="update",
                installed_version=latest_int,
            )
            progress("HorizonXI game is already up to date.", 1.0)
            return

        patch_count = len(patches)
        patch_span = 0.95 / patch_count
        base_start = 0.05

        for index, archive in enumerate(patches):
            archive_start = base_start + (patch_span * index)
            download_start = archive_start
            extract_start = archive_start + (patch_span * 0.72)
            archive_end = archive_start + patch_span

            archive_path = self.download_game_archive(
                archive,
                stage_progress(download_start, extract_start),
            )
            self.apply_delete_files(archive)
            self.extract_game_archive(
                archive_path,
                stage_progress(extract_start, archive_end),
            )

        self._write_linux_installer_marker(
            manifest={"latestVersion": latest_int, "updateData": update_manifest},
            archives=patches,
            install_type="update",
            installed_version=latest_int,
        )

        progress("HorizonXI game update complete.", 1.0)

    def repair(self, progress_callback=None):
        self.install(progress_callback)

    def remove(self):
        if self.game_dir.exists():
            shutil.rmtree(self.game_dir)


    def save_default_configuration_snapshot(self, overwrite=False):
        """Capture installed default addon/plugin config for reset buttons."""
        AddonManager().snapshot_defaults(overwrite=overwrite)
        PluginManager().snapshot_defaults(overwrite=overwrite)

    def run_post_install_helpers(self, proton_path: str, progress_callback=None):
        """Apply required Wine-prefix setup after the game files are present."""
        ensure_umu_run_available()
        env = self._build_wine_env(proton_path)

        steps = [
            ("Applying HorizonXI registry settings", self._run_registry_helper),
            ("Installing Microsoft VC++ 2015-2022 x86 runtime", self._run_vc_redist_x86),
        ]

        total = len(steps)
        for index, (description, step_func) in enumerate(steps, start=1):
            start_fraction = (index - 1) / total
            end_fraction = index / total

            if progress_callback:
                progress_callback(f"{description}...", start_fraction)

            step_func(env)

            if progress_callback:
                progress_callback(f"{description} complete.", end_fraction)

    def _build_wine_env(self, proton_path: str):
        env = os.environ.copy()
        env["WINEPREFIX"] = str(PREFIX_DIR)
        env["PROTONPATH"] = str(proton_path)
        env["WINEDLLOVERRIDES"] = "d3d8=n,b"
        return env

    def _run_registry_helper(self, env):
        registry_exe = self.game_dir / "DONTTOUCH_Registry.exe"
        if not registry_exe.exists():
            return

        command = _umu_command(
            ["./DONTTOUCH_Registry.exe", "/S"],
            env=env,
            cwd=self.game_dir,
        )

        subprocess.run(
            command,
            cwd=str(self.game_dir) if not IS_FLATPAK else None,
            env=env if not IS_FLATPAK else None,
            check=False,
        )

    def _run_vc_redist_x86(self, env):
        vc_redist = (
            self.prereqs_dir
            / "Visual C++ Redistributable for Visual Studio 2015-2022"
            / "VC_redist.x86.exe"
        )

        if not vc_redist.exists():
            raise RuntimeError(f"Required VC++ redistributable not found: {vc_redist}")

        command = _umu_command(
            [
                str(vc_redist),
                "/install",
                "/quiet",
                "/norestart",
            ],
            env=env,
            cwd=self.game_dir,
        )

        print()
        print("================================================")
        print("Installing VC++ 2015-2022 x86 Runtime")
        print("Working directory:", self.game_dir)
        print("Installer path:", vc_redist)
        print("Command:", " ".join(command))
        print("================================================")

        result = subprocess.run(
            command,
            cwd=str(self.game_dir) if not IS_FLATPAK else None,
            env=env if not IS_FLATPAK else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

        if result.stdout:
            print(result.stdout)

        print("VC_REDIST_X86_EXIT_CODE =", result.returncode)

        if result.returncode not in (0, 3010, 1638):
            raise RuntimeError(
                "VC++ 2015-2022 x86 runtime installer failed "
                f"with exit code {result.returncode}. See terminal output above for details."
            )

    def fetch_json(self, url: str):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "HorizonXI-Linux-Launcher/0.1"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_install_manifest(self):
        payload = self.fetch_json(INSTALL_GAME_URL)
        if not isinstance(payload, dict):
            raise RuntimeError("HorizonXI install API returned an unexpected response.")
        return payload

    def fetch_latest_version(self):
        payload = self.fetch_json(LATEST_VERSION_URL)
        if isinstance(payload, dict):
            version = payload.get("latestVersion")
        else:
            version = payload

        if version is None:
            raise RuntimeError("HorizonXI latest-version API did not return latestVersion.")

        return version

    def fetch_update_manifest(self, current_version: int):
        query = urllib.parse.urlencode({"ver": current_version})
        payload = self.fetch_json(f"{UPDATE_GAME_URL}?{query}")

        if isinstance(payload, dict):
            return payload.get("updateData", payload.get("updates", payload.get("data", [])))

        if isinstance(payload, list):
            return payload

        raise RuntimeError("HorizonXI update API returned an unexpected response.")

    def build_fresh_install_plan(self, manifest: dict):
        install_data = manifest.get("installData") or {}

        archives = []

        base_magnet = self._first_present(
            install_data,
            "baseGameMagnetLink",
            "baseMagnetLink",
            "magnetLink",
            "magnet",
        )
        base_name = self._first_present(
            install_data,
            "baseZipName",
            "zipName",
            "fileName",
            "filename",
            "name",
        ) or self._filename_from_magnet(base_magnet) or "HorizonXI.zip"

        if base_magnet:
            archives.append(
                {
                    "name": base_name,
                    "magnet": base_magnet,
                    "version": self._first_present(install_data, "baseGameVersion", "version"),
                    "marketing_version": self._first_present(
                        install_data,
                        "baseGameMarketingVersion",
                        "marketingVersion",
                        "marketing_version",
                    ),
                    "kind": "base",
                }
            )

        update_data = manifest.get("updateData") or []
        archives.extend(self.build_update_plan(update_data))

        return archives

    def build_update_plan(self, update_data):
        if isinstance(update_data, dict):
            update_data = update_data.get("updateData", update_data.get("updates", update_data.get("data", [])))

        if not isinstance(update_data, list):
            raise RuntimeError("HorizonXI update data was not a list.")

        archives = []
        for item in update_data:
            if not isinstance(item, dict):
                continue

            magnet = self._first_present(
                item,
                "magnetLink",
                "gameMagnetLink",
                "patchMagnetLink",
                "updateMagnetLink",
                "magnet",
            )
            if not magnet:
                continue

            name = (
                self._first_present(item, "updateZipName", "zipName", "fileName", "filename", "name")
                or self._filename_from_magnet(magnet)
            )

            if not name:
                raise RuntimeError(f"Could not determine zip name for update magnet: {magnet[:80]}...")

            archives.append(
                {
                    "name": name,
                    "magnet": magnet,
                    "version": self._first_present(item, "version", "gameVersion", "id"),
                    "marketing_version": self._first_present(
                        item,
                        "marketingVersion",
                        "gameMarketingVersion",
                        "marketing_version",
                    ),
                    "kind": "patch",
                    "delete_files": item.get("deleteFiles") or [],
                }
            )

        return archives


    def apply_delete_files(self, archive: dict):
        """Apply file deletions requested by update metadata.

        Horizon patch metadata can include paths that should be removed before
        the patch is extracted. Paths are relative to the Game directory.
        """
        delete_files = archive.get("delete_files") or []
        if not delete_files:
            return

        game_root = self.game_dir.resolve()

        for relative_name in delete_files:
            if not isinstance(relative_name, str) or not relative_name.strip():
                continue

            candidate = (self.game_dir / Path(*PurePosixPath(relative_name).parts)).resolve()
            if not self._is_relative_to(candidate, game_root):
                raise RuntimeError(f"Blocked unsafe delete path from update metadata: {relative_name}")

            if candidate.exists() and candidate.is_file():
                candidate.unlink()

    def download_prereqs(self, progress_callback=None) -> Path:
        self.ensure_dirs()
        archive_path = self.downloads_dir / PREREQS_ARCHIVE["name"]

        if archive_path.exists() and archive_path.stat().st_size > 0:
            if progress_callback:
                progress_callback("prereqs.zip already downloaded.", 1.0)
            return archive_path

        if progress_callback:
            progress_callback("Downloading prereqs.zip...", 0.0)

        def reporthook(block_count, block_size, total_size):
            if not progress_callback or total_size <= 0:
                return
            downloaded = min(block_count * block_size, total_size)
            fraction = downloaded / total_size
            percent = int(fraction * 100)
            progress_callback(f"Downloading prereqs.zip... {percent}%", fraction)

        urllib.request.urlretrieve(
            PREREQS_ARCHIVE["url"],
            archive_path,
            reporthook=reporthook,
        )

        if progress_callback:
            progress_callback("prereqs.zip download complete.", 1.0)

        return archive_path

    def extract_prereqs(self, archive_path: Path, progress_callback=None):
        if self.prereqs_dir.exists() and any(self.prereqs_dir.iterdir()):
            if progress_callback:
                progress_callback("Prerequisites already extracted.", 1.0)
            return

        self.prereqs_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback("Extracting prerequisites...", 0.0)

        self._safe_extract_zip(
            archive_path,
            self.prereqs_dir,
            progress_callback,
            strip_top_level="Launcher-Prereqs-main",
        )

        if progress_callback:
            progress_callback("Prerequisites extracted.", 1.0)

    def download_game_archive(self, archive: dict, progress_callback=None) -> Path:
        self.ensure_dirs()
        return self.torrent_downloader.download(
            archive["magnet"],
            archive["name"],
            progress_callback,
        )

    def extract_game_archive(self, archive_path: Path, progress_callback=None):
        self.ensure_dirs()

        if progress_callback:
            progress_callback(f"Extracting {archive_path.name}...", 0.0)

        self._safe_extract_zip(
            archive_path,
            self.game_dir,
            progress_callback,
            strip_top_level="HorizonXI",
        )

        if progress_callback:
            progress_callback(f"{archive_path.name} extracted.", 1.0)

    def _write_linux_installer_marker(
        self,
        manifest: dict,
        archives: list,
        install_type: str,
        installed_version=None,
    ):
        previous = self._read_marker()

        latest_version = installed_version
        if latest_version is None:
            latest_version = manifest.get("latestVersion") if isinstance(manifest, dict) else None

        marketing_version = self._best_marketing_version(manifest, archives) or previous.get("installedMarketingVersion")

        marker = {
            "installed_by": "HorizonXI Linux Launcher",
            "installType": install_type,
            "installedVersion": latest_version,
            "installedMarketingVersion": marketing_version,
            "archives": [archive.get("name") for archive in archives],
        }

        self.marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

    def _read_marker(self):
        if not self.marker_path.exists():
            return {}

        try:
            data = json.loads(self.marker_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _best_marketing_version(self, manifest: dict, archives: list):
        for archive in reversed(archives):
            if archive.get("marketing_version"):
                return archive["marketing_version"]

        if isinstance(manifest, dict):
            update_data = manifest.get("updateData") or []
            if isinstance(update_data, list):
                for item in reversed(update_data):
                    if isinstance(item, dict):
                        value = self._first_present(
                            item,
                            "marketingVersion",
                            "gameMarketingVersion",
                            "marketing_version",
                        )
                        if value:
                            return value

            install_data = manifest.get("installData") or {}
            if isinstance(install_data, dict):
                return self._first_present(
                    install_data,
                    "latestMarketingVersion",
                    "baseGameMarketingVersion",
                    "marketingVersion",
                    "marketing_version",
                )

        return None

    @staticmethod
    def _first_present(mapping: dict, *keys):
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _filename_from_magnet(magnet: str | None):
        if not magnet:
            return None

        parsed = urllib.parse.urlparse(magnet)
        query = urllib.parse.parse_qs(parsed.query)
        dn = query.get("dn", [None])[0]
        if dn:
            return urllib.parse.unquote(dn)
        return None

    def _safe_extract_zip(
        self,
        archive_path: Path,
        target_dir: Path,
        progress_callback=None,
        strip_top_level: str | None = None,
    ):
        archive_path = Path(archive_path)
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        target_root = target_dir.resolve()

        with zipfile.ZipFile(archive_path, "r") as archive:
            members = archive.infolist()
            total = len(members)

            for index, member in enumerate(members, start=1):
                relative_path = self._normalise_zip_member_path(
                    member.filename,
                    strip_top_level=strip_top_level,
                )

                if relative_path is None:
                    if progress_callback and total > 0:
                        fraction = index / total
                        percent = int(fraction * 100)
                        progress_callback(
                            f"Extracting {archive_path.name}... {percent}%",
                            fraction,
                        )
                    continue

                destination = (target_dir / relative_path).resolve()
                if not self._is_relative_to(destination, target_root):
                    raise RuntimeError(f"Blocked unsafe zip path: {member.filename}")

                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member, "r") as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)

                if progress_callback and total > 0:
                    fraction = index / total
                    percent = int(fraction * 100)
                    progress_callback(f"Extracting {archive_path.name}... {percent}%", fraction)

    @staticmethod
    def _normalise_zip_member_path(
        member_name: str,
        strip_top_level: str | None = None,
    ) -> Path | None:
        parts = [
            part
            for part in PurePosixPath(member_name).parts
            if part not in ("", ".")
        ]

        if not parts:
            return None

        if any(part == ".." for part in parts):
            raise RuntimeError(f"Blocked unsafe zip path: {member_name}")

        if strip_top_level and parts[0].lower() == strip_top_level.lower():
            parts = parts[1:]

        if not parts:
            return None

        return Path(*parts)

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
