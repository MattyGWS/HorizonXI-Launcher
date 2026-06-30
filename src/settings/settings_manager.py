import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from config import ASHITA_BOOT_CONFIG, DATA_DIR, GAME_DIR, UMU_RUN, PREFIX_DIR, PROTON_DIR


DEFAULT_SETTINGS_SNAPSHOT = DATA_DIR / "default-settings-ashita.ini"


@dataclass
class GameSettings:
    hardware_mouse: bool
    play_opening_movie: bool
    sound: bool
    always_play_sound: bool
    max_sounds: int
    language: str
    window_mode: str
    window_width: int
    window_height: int
    background_width: int
    background_height: int
    menu_width: int
    menu_height: int
    gamma: float
    graphics_stabilization: bool
    map_compression: bool
    bump_mapping: bool
    maintain_aspect_ratio: bool
    lcd_mode: bool
    environment: int
    textures: int
    fonts: int
    mip_mapping: int


class SettingsManager:
    SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    KEY_RE = re.compile(r"^\s*([^#;][^=]*?)\s*=\s*(.*?)\s*$")

    WINDOW_MODES = {
        "Fullscreen": 0,
        "Window": 1,
        "Fullscreen Windowed": 2,
        "Borderless Windowed": 3,
    }
    WINDOW_MODE_LABELS = {value: key for key, value in WINDOW_MODES.items()}

    LANGUAGES = {
        "English": 2,
        "Japanese": 1,
    }
    LANGUAGE_LABELS = {value: key for key, value in LANGUAGES.items()}

    def is_available(self):
        return ASHITA_BOOT_CONFIG.exists()

    def ensure_default_snapshot(self):
        if not self.is_available():
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not DEFAULT_SETTINGS_SNAPSHOT.exists():
            shutil.copy2(ASHITA_BOOT_CONFIG, DEFAULT_SETTINGS_SNAPSHOT)

    def reset_to_default(self):
        if not DEFAULT_SETTINGS_SNAPSHOT.exists():
            self.ensure_default_snapshot()
        if not DEFAULT_SETTINGS_SNAPSHOT.exists():
            raise RuntimeError("No default settings snapshot is available yet.")
        shutil.copy2(DEFAULT_SETTINGS_SNAPSHOT, ASHITA_BOOT_CONFIG)

    def read_settings(self):
        data = self._read_ini()
        reg = data.get("ffxi.registry", {})
        input_section = data.get("ashita.input", {})
        lang = data.get("ashita.language", {})

        return GameSettings(
            hardware_mouse=self._get_bool(reg, "0021", self._get_bool(input_section, "mouse.unhook", True)),
            play_opening_movie=self._get_bool(reg, "0022", False),
            sound=self._get_bool(reg, "0007", True),
            always_play_sound=self._get_bool(reg, "0035", True),
            max_sounds=self._get_int(reg, "0029", 20),
            language=self.LANGUAGE_LABELS.get(self._get_int(lang, "ashita", 2), "English"),
            window_mode=self.WINDOW_MODE_LABELS.get(self._get_int(reg, "0034", 1), "Window"),
            window_width=self._get_int(reg, "0001", 1920),
            window_height=self._get_int(reg, "0002", 1080),
            background_width=self._get_int(reg, "0003", 4096),
            background_height=self._get_int(reg, "0004", 4096),
            menu_width=self._get_int(reg, "0037", self._get_int(reg, "0001", 1920)),
            menu_height=self._get_int(reg, "0038", self._get_int(reg, "0002", 1080)),
            gamma=self._get_float(reg, "0028", 0.0),
            graphics_stabilization=self._get_bool(reg, "0040", False),
            map_compression=not self._get_bool(reg, "0019", True),
            bump_mapping=self._get_bool(reg, "0017", True),
            maintain_aspect_ratio=self._get_bool(reg, "0044", True),
            lcd_mode=self._get_bool(reg, "0030", False),
            environment=self._get_int(reg, "0011", 2),
            textures=self._get_int(reg, "0018", 2),
            fonts=self._get_int(reg, "0036", 1),
            mip_mapping=self._get_int(reg, "0000", 6),
        )

    def write_settings(self, settings: GameSettings):
        if not self.is_available():
            raise RuntimeError("Game settings file not found. Install HorizonXI first.")
        self.ensure_default_snapshot()

        updates = {
            ("ashita.input", "mouse.unhook"): "1" if settings.hardware_mouse else "0",
            ("ashita.language", "playonline"): str(self.LANGUAGES.get(settings.language, 2)),
            ("ashita.language", "ashita"): str(self.LANGUAGES.get(settings.language, 2)),
            ("ffxi.registry", "0000"): str(settings.mip_mapping),
            ("ffxi.registry", "0001"): str(settings.window_width),
            ("ffxi.registry", "0002"): str(settings.window_height),
            ("ffxi.registry", "0003"): str(settings.background_width),
            ("ffxi.registry", "0004"): str(settings.background_height),
            ("ffxi.registry", "0007"): "1" if settings.sound else "0",
            ("ffxi.registry", "0011"): str(settings.environment),
            ("ffxi.registry", "0017"): "1" if settings.bump_mapping else "0",
            ("ffxi.registry", "0018"): str(settings.textures),
            # 0019: 0 = compressed, 1 = uncompressed. UI asks "Map Compression".
            ("ffxi.registry", "0019"): "0" if settings.map_compression else "1",
            ("ffxi.registry", "0021"): "1" if settings.hardware_mouse else "0",
            ("ffxi.registry", "0022"): "1" if settings.play_opening_movie else "0",
            ("ffxi.registry", "0028"): self._format_float(settings.gamma),
            ("ffxi.registry", "0029"): str(settings.max_sounds),
            ("ffxi.registry", "0030"): "1" if settings.lcd_mode else "0",
            ("ffxi.registry", "0034"): str(self.WINDOW_MODES.get(settings.window_mode, 1)),
            ("ffxi.registry", "0035"): "1" if settings.always_play_sound else "0",
            ("ffxi.registry", "0036"): str(settings.fonts),
            ("ffxi.registry", "0037"): str(settings.menu_width),
            ("ffxi.registry", "0038"): str(settings.menu_height),
            ("ffxi.registry", "0040"): "1" if settings.graphics_stabilization else "0",
            ("ffxi.registry", "0044"): "1" if settings.maintain_aspect_ratio else "0",
        }
        self._write_ini_updates(updates)

    def open_gamepad_config(self):
        candidates = [
            GAME_DIR / "SquareEnix" / "FINAL FANTASY XI" / "ToolsUS" / "FFXiPadConfig.exe",
            GAME_DIR / "SquareEnix" / "FINAL FANTASY XI" / "ToolsEU" / "FFXiPadConfig.exe",
            GAME_DIR / "SquareEnix" / "FINAL FANTASY XI" / "Tools" / "FFXiPadConfig.exe",
            GAME_DIR / "SquareEnix" / "FINAL FANTASY XI" / "FFXiPadConfig.exe",
            GAME_DIR / "FFXiPadConfig.exe",
        ]
        exe = next((path for path in candidates if path.exists()), None)
        if exe is None:
            raise RuntimeError("Could not find FFXiPadConfig.exe in the game install.")

        try:
            UMU_RUN.chmod(UMU_RUN.stat().st_mode | 0o111)
        except Exception:
            pass

        env = dict(**__import__("os").environ)
        env["WINEPREFIX"] = str(PREFIX_DIR)
        env["PROTONPATH"] = str(PROTON_DIR / "GE-Proton7-42")
        env["WINEDLLOVERRIDES"] = "d3d8=n,b"

        subprocess.Popen([str(UMU_RUN), str(exe)], cwd=str(exe.parent), env=env)

    def _read_ini(self):
        if not self.is_available():
            return {}
        current = None
        data = {}
        for line in ASHITA_BOOT_CONFIG.read_text(encoding="utf-8", errors="replace").splitlines():
            sec = self.SECTION_RE.match(line)
            if sec:
                current = sec.group(1).strip()
                data.setdefault(current, {})
                continue
            key = self.KEY_RE.match(line)
            if current and key:
                data[current][key.group(1).strip()] = key.group(2).strip()
        return data

    def _write_ini_updates(self, updates):
        lines = ASHITA_BOOT_CONFIG.read_text(encoding="utf-8", errors="replace").splitlines()
        remaining = dict(updates)
        output = []
        current = None
        seen_section = set()

        for line in lines:
            sec = self.SECTION_RE.match(line)
            if sec:
                previous = current
                # Append any missing keys for the previous section before moving on.
                if previous:
                    for (section, key), value in list(remaining.items()):
                        if section == previous:
                            output.append(f"{key} = {value}")
                            remaining.pop((section, key), None)
                current = sec.group(1).strip()
                seen_section.add(current)
                output.append(line)
                continue

            key_match = self.KEY_RE.match(line)
            if current and key_match:
                key = key_match.group(1).strip()
                update_key = (current, key)
                if update_key in remaining:
                    output.append(f"{key} = {remaining.pop(update_key)}")
                    continue

            output.append(line)

        if current:
            for (section, key), value in list(remaining.items()):
                if section == current:
                    output.append(f"{key} = {value}")
                    remaining.pop((section, key), None)

        # Add any missing sections.
        for (section, key), value in list(remaining.items()):
            if section not in seen_section:
                output.append("")
                output.append(f"[{section}]")
                seen_section.add(section)
            output.append(f"{key} = {value}")

        ASHITA_BOOT_CONFIG.write_text("\n".join(output) + "\n", encoding="utf-8")

    @staticmethod
    def _get_int(section, key, default):
        try:
            return int(str(section.get(key, default)).split(",")[0])
        except Exception:
            return default

    @staticmethod
    def _get_float(section, key, default):
        try:
            return float(section.get(key, default))
        except Exception:
            return default

    @staticmethod
    def _get_bool(section, key, default):
        try:
            return int(str(section.get(key, "1" if default else "0"))) != 0
        except Exception:
            return default

    @staticmethod
    def _format_float(value):
        if abs(value - int(value)) < 0.0001:
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
