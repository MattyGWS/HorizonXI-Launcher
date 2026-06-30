import configparser
import re
from dataclasses import dataclass
from pathlib import Path

from config import ASHITA_BOOT_CONFIG, GAME_DIR


PLUGINS_START = "# --HORIZON_PLUGINS_START--"
PLUGINS_STOP = "# --HORIZON_PLUGINS_STOP--"
DEFAULT_SCRIPT_SNAPSHOT = "linux-launcher-default-script.txt"
DEFAULT_ASHITA_SNAPSHOT = "linux-launcher-default-ashita.ini"


@dataclass(frozen=True)
class PluginInfo:
    name: str
    source: str
    path: Path | None = None
    enabled: bool = False


@dataclass(frozen=True)
class PolPluginInfo:
    name: str
    enabled: bool = False


class PluginManager:
    """Manage Ashita plugins/extensions.

    Ashita plugins are normally loaded from scripts/default.txt using lines like:
        /load screenshot

    PlayOnline plugins are controlled by config/boot/ashita.ini under:
        [ashita.polplugins]
        sandbox = 1
        pivot = 1

    This manager edits only those bounded launcher-owned areas and preserves the
    rest of the user's script/config.
    """

    def __init__(self):
        self.game_dir = GAME_DIR
        self.plugins_dir = self.game_dir / "plugins"
        self.polplugins_dir = self.game_dir / "polplugins"
        self.default_script = self.game_dir / "scripts" / "default.txt"
        self.ashita_config = ASHITA_BOOT_CONFIG

    def is_available(self):
        return self.game_dir.exists() and self.default_script.exists()

    def snapshot_defaults(self, overwrite=False):
        """Save installed default plugin / extension config for later reset operations."""
        saved_any = False

        if self.default_script.exists():
            script_snapshot = self.game_dir / DEFAULT_SCRIPT_SNAPSHOT
            if overwrite or not script_snapshot.exists():
                script_snapshot.write_text(
                    self.default_script.read_text(encoding="utf-8", errors="ignore"),
                    encoding="utf-8",
                )
                saved_any = True

        if self.ashita_config.exists():
            ashita_snapshot = self.game_dir / DEFAULT_ASHITA_SNAPSHOT
            if overwrite or not ashita_snapshot.exists():
                ashita_snapshot.write_text(
                    self.ashita_config.read_text(encoding="utf-8", errors="ignore"),
                    encoding="utf-8",
                )
                saved_any = True

        return saved_any

    def reset_plugins_to_default(self):
        """Restore only launcher-managed plugin blocks/sections from saved defaults."""
        self._reset_ashita_plugin_block_to_default()
        self._reset_polplugins_to_default()

    def _reset_ashita_plugin_block_to_default(self):
        snapshot_path = self.game_dir / DEFAULT_SCRIPT_SNAPSHOT
        if not snapshot_path.exists():
            if not self.snapshot_defaults(overwrite=False):
                raise RuntimeError("Default plugin snapshot was not found.")

        current_lines = self._read_default_lines()
        default_lines = snapshot_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        current_start, current_stop = self._find_plugin_block(current_lines)
        default_start, default_stop = self._find_plugin_block(default_lines)

        if default_start is None or default_stop is None:
            raise RuntimeError("Saved default script does not contain a Horizon plugin block.")

        if current_start is None or current_stop is None:
            current_lines = self._append_plugin_block(current_lines)
            current_start, current_stop = self._find_plugin_block(current_lines)

        new_lines = (
            current_lines[: current_start + 1]
            + default_lines[default_start + 1: default_stop]
            + current_lines[current_stop:]
        )

        self.default_script.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def _reset_polplugins_to_default(self):
        snapshot_path = self.game_dir / DEFAULT_ASHITA_SNAPSHOT
        if not snapshot_path.exists():
            if not self.snapshot_defaults(overwrite=False):
                raise RuntimeError("Default ashita.ini snapshot was not found.")

        default_parser = configparser.ConfigParser()
        default_parser.optionxform = str
        default_parser.read(snapshot_path, encoding="utf-8")

        current_parser = self._read_ashita_config()

        if current_parser.has_section("ashita.polplugins"):
            current_parser.remove_section("ashita.polplugins")

        if default_parser.has_section("ashita.polplugins"):
            current_parser.add_section("ashita.polplugins")
            for name, value in default_parser.items("ashita.polplugins"):
                current_parser.set("ashita.polplugins", name, value)

        self.ashita_config.parent.mkdir(parents=True, exist_ok=True)
        with self.ashita_config.open("w", encoding="utf-8") as handle:
            current_parser.write(handle, space_around_delimiters=True)

    def scan_plugins(self):
        enabled = self.get_enabled_plugins()
        plugins_by_key = {}

        if self.plugins_dir.exists():
            for dll_path in sorted(self.plugins_dir.glob("*.dll"), key=lambda p: p.name.lower()):
                name = dll_path.stem
                plugins_by_key[name.lower()] = PluginInfo(
                    name=name,
                    source=f"plugins/{dll_path.name}",
                    path=dll_path,
                    enabled=name.lower() in enabled,
                )

        # Keep enabled plugin names visible even if the DLL name could not be
        # matched. This avoids silently hiding/removing custom script entries.
        for enabled_name in sorted(enabled):
            if enabled_name not in plugins_by_key:
                plugins_by_key[enabled_name] = PluginInfo(
                    name=enabled_name,
                    source="scripts/default.txt",
                    path=None,
                    enabled=True,
                )

        return sorted(plugins_by_key.values(), key=lambda item: item.name.lower())

    def scan_polplugins(self):
        configured = self.get_polplugin_states()
        names = set(configured.keys())

        if self.polplugins_dir.exists():
            for child in self.polplugins_dir.iterdir():
                if child.is_dir():
                    names.add(child.name.lower())
                elif child.suffix.lower() == ".dll":
                    names.add(child.stem.lower())

        return [
            PolPluginInfo(name=name, enabled=bool(configured.get(name, False)))
            for name in sorted(names)
        ]

    def get_enabled_plugins(self):
        lines = self._read_default_lines()
        start, stop = self._find_plugin_block(lines)
        enabled = set()

        if start is None or stop is None:
            return enabled

        for line in lines[start + 1:stop]:
            match = re.match(r"^\s*/load\s+(.+?)\s*$", line, re.IGNORECASE)
            if match:
                enabled.add(match.group(1).strip().lower())

        return enabled

    def set_plugin_enabled(self, plugin_name, enabled):
        plugin_name = plugin_name.strip()
        if not plugin_name:
            return

        lines = self._read_default_lines()
        start, stop = self._find_plugin_block(lines)

        if start is None or stop is None:
            lines = self._append_plugin_block(lines)
            start, stop = self._find_plugin_block(lines)

        before = lines[: start + 1]
        block = lines[start + 1: stop]
        after = lines[stop:]

        existing_names = []
        other_lines = []

        for line in block:
            match = re.match(r"^\s*/load\s+(.+?)\s*$", line, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name.lower() != plugin_name.lower():
                    existing_names.append(name)
            elif line.strip():
                other_lines.append(line)

        if enabled:
            existing_names.append(plugin_name)

        deduped = []
        seen = set()
        for name in existing_names:
            key = name.lower()
            if key not in seen:
                deduped.append(name)
                seen.add(key)

        new_block = [f"/load {name}" for name in deduped]

        if other_lines:
            if new_block:
                new_block.append("")
            new_block.extend(other_lines)

        self.default_script.parent.mkdir(parents=True, exist_ok=True)
        self.default_script.write_text("\n".join(before + new_block + after) + "\n", encoding="utf-8")

    def get_polplugin_states(self):
        if not self.ashita_config.exists():
            return {}

        parser = self._read_ashita_config()
        if not parser.has_section("ashita.polplugins"):
            return {}

        states = {}
        for name, value in parser.items("ashita.polplugins"):
            states[name.lower()] = self._truthy(value)
        return states

    def set_polplugin_enabled(self, plugin_name, enabled):
        plugin_name = plugin_name.strip()
        if not plugin_name:
            return

        parser = self._read_ashita_config()
        if not parser.has_section("ashita.polplugins"):
            parser.add_section("ashita.polplugins")

        parser.set("ashita.polplugins", plugin_name, "1" if enabled else "0")

        self.ashita_config.parent.mkdir(parents=True, exist_ok=True)
        with self.ashita_config.open("w", encoding="utf-8") as handle:
            parser.write(handle, space_around_delimiters=True)

    def _read_default_lines(self):
        if not self.default_script.exists():
            return []
        return self.default_script.read_text(encoding="utf-8", errors="ignore").splitlines()

    def _find_plugin_block(self, lines):
        start = None
        stop = None
        for index, line in enumerate(lines):
            if line.strip() == PLUGINS_START:
                start = index
            elif line.strip() == PLUGINS_STOP and start is not None:
                stop = index
                break
        return start, stop

    def _append_plugin_block(self, lines):
        if lines and lines[-1].strip():
            lines.append("")

        lines.extend(
            [
                "##########################################################################",
                "#",
                "# Horizon Launcher Controlled Plugins",
                "#",
                "##########################################################################",
                PLUGINS_START,
                PLUGINS_STOP,
                "",
            ]
        )
        return lines

    def _read_ashita_config(self):
        parser = configparser.ConfigParser()
        parser.optionxform = str
        if self.ashita_config.exists():
            parser.read(self.ashita_config, encoding="utf-8")
        return parser

    def _truthy(self, value):
        return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}
