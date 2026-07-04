import re
from dataclasses import dataclass
from pathlib import Path

from config import GAME_DIR


ADDONS_START = "# --HORIZON_ADDONS_START--"
ADDONS_STOP = "# --HORIZON_ADDONS_STOP--"
DEFAULT_SCRIPT_SNAPSHOT = "linux-launcher-default-script.txt"
PROHIBITED_ADDON_FALLBACK_NOTE = "This addon is listed as prohibited by HorizonXI."


@dataclass(frozen=True)
class AddonInfo:
    name: str
    folder: str
    lua_path: Path
    description: str = ""
    enabled: bool = False
    prohibited: bool = False
    prohibited_note: str = ""


class AddonManager:
    def __init__(self):
        self.game_dir = GAME_DIR
        self.addons_dir = self.game_dir / "addons"
        self.default_script = self.game_dir / "scripts" / "default.txt"
        # Filled by the UI from https://horizonxi.com/addons.json.
        # Keeping this here makes prohibited-addon blocking happen at the
        # file-writing layer too, not only in the visible GTK rows.
        self.prohibited_addons = {}

    def is_available(self):
        return self.addons_dir.exists() and self.default_script.exists()

    def snapshot_defaults(self, overwrite=False):
        """Save the installed default script for later reset operations."""
        if not self.default_script.exists():
            return False

        snapshot_path = self.game_dir / DEFAULT_SCRIPT_SNAPSHOT
        if snapshot_path.exists() and not overwrite:
            return False

        snapshot_path.write_text(
            self.default_script.read_text(encoding="utf-8", errors="ignore"),
            encoding="utf-8",
        )
        return True

    def reset_addons_to_default(self):
        """Restore only the Horizon addon block from the saved default script."""
        snapshot_path = self.game_dir / DEFAULT_SCRIPT_SNAPSHOT
        if not snapshot_path.exists():
            # Capture the current file as a fallback for installs made before this feature existed.
            if not self.snapshot_defaults(overwrite=False):
                raise RuntimeError("Default addon snapshot was not found.")

        current_lines = self._read_lines()
        default_lines = snapshot_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        current_start, current_stop = self._find_block(current_lines)
        default_start, default_stop = self._find_block(default_lines)

        if default_start is None or default_stop is None:
            raise RuntimeError("Saved default script does not contain a Horizon addon block.")

        if current_start is None or current_stop is None:
            current_lines = self._append_addon_block(current_lines)
            current_start, current_stop = self._find_block(current_lines)

        new_lines = (
            current_lines[: current_start + 1]
            + default_lines[default_start + 1: default_stop]
            + current_lines[current_stop:]
        )

        self.default_script.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def scan_addons(self):
        enabled = self.get_enabled_addons()
        addons = []

        if not self.addons_dir.exists():
            return addons

        for folder in sorted(self.addons_dir.iterdir(), key=lambda p: p.name.lower()):
            if not folder.is_dir():
                continue

            lua_path = self._find_main_lua(folder)
            if not lua_path:
                continue

            addon_name = self._read_addon_name(lua_path) or folder.name
            addon_description = self._read_addon_description(lua_path) or "No description provided."
            prohibited_info = self.get_prohibited_addon_info(addon_name, folder.name)
            is_prohibited = prohibited_info is not None
            prohibited_note = ""

            if is_prohibited:
                prohibited_note = str(
                    prohibited_info.get("note")
                    or PROHIBITED_ADDON_FALLBACK_NOTE
                ).strip()
                addon_description = prohibited_note

            addons.append(
                AddonInfo(
                    name=addon_name,
                    folder=folder.name,
                    lua_path=lua_path,
                    description=addon_description,
                    enabled=(not is_prohibited and addon_name.lower() in enabled),
                    prohibited=is_prohibited,
                    prohibited_note=prohibited_note,
                )
            )

        return addons

    def set_prohibited_addons(self, prohibited_addons):
        """Set the HorizonXI Ashita prohibited-addon policy map.

        Expected input is a dict keyed by addon name, with values such as
        {"name": "Casper", "note": "..."}. The manager stores normalized
        keys so checks are case-insensitive.
        """
        self.prohibited_addons = {}

        if not isinstance(prohibited_addons, dict):
            return

        for key, value in prohibited_addons.items():
            if isinstance(value, dict):
                display_name = str(value.get("name") or key or "").strip()
                if not display_name:
                    continue
                item = dict(value)
                item["name"] = display_name
            else:
                display_name = str(key or value or "").strip()
                if not display_name:
                    continue
                item = {"name": display_name}

            item["note"] = str(item.get("note") or PROHIBITED_ADDON_FALLBACK_NOTE).strip()

            for policy_key in self._policy_name_keys(display_name):
                self.prohibited_addons[policy_key] = item

    def is_addon_prohibited(self, addon_name, addon_folder=None):
        return self.get_prohibited_addon_info(addon_name, addon_folder) is not None

    def get_prohibited_addon_info(self, addon_name, addon_folder=None):
        for candidate in (addon_name, addon_folder):
            for key in self._policy_name_keys(candidate):
                if key in self.prohibited_addons:
                    return self.prohibited_addons[key]
        return None

    def disable_addon_everywhere(self, addon_name, addon_folder=None):
        """Remove possible load lines for both display name and folder name."""
        names = []
        for candidate in (addon_name, addon_folder):
            candidate = str(candidate or "").strip()
            if candidate and candidate.lower() not in [name.lower() for name in names]:
                names.append(candidate)

        for name in names:
            self.set_addon_enabled(name, False)

    def _normalize_policy_name(self, name):
        return str(name or "").strip().casefold()

    def _compact_policy_name(self, name):
        # Helpful for minor formatting differences such as "No-ckback" vs
        # "nockback", while still avoiding broad/fuzzy matching.
        return re.sub(r"[^a-z0-9]+", "", self._normalize_policy_name(name))

    def _policy_name_keys(self, name):
        normalized = self._normalize_policy_name(name)
        if not normalized:
            return []

        keys = [normalized]
        compact = self._compact_policy_name(normalized)
        if compact and compact != normalized:
            keys.append(compact)
        return keys

    def get_enabled_addons(self):
        lines = self._read_lines()
        start, stop = self._find_block(lines)
        enabled = set()

        if start is None or stop is None:
            return enabled

        for line in lines[start + 1:stop]:
            match = re.match(r"^\s*/addon\s+load\s+(.+?)\s*$", line, re.IGNORECASE)
            if match:
                enabled.add(match.group(1).strip().lower())

        return enabled

    def set_addon_enabled(self, addon_name, enabled):
        addon_name = addon_name.strip()
        if not addon_name:
            return

        # Prohibited addons are never written as enabled, even if some future
        # UI path accidentally asks for it.
        if enabled and self.is_addon_prohibited(addon_name):
            enabled = False

        lines = self._read_lines()
        start, stop = self._find_block(lines)

        if start is None or stop is None:
            lines = self._append_addon_block(lines)
            start, stop = self._find_block(lines)

        before = lines[: start + 1]
        block = lines[start + 1: stop]
        after = lines[stop:]

        existing_names = []
        other_lines = []

        for line in block:
            match = re.match(r"^\s*/addon\s+load\s+(.+?)\s*$", line, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name.lower() != addon_name.lower():
                    existing_names.append(name)
            elif line.strip():
                other_lines.append(line)

        if enabled:
            existing_names.append(addon_name)

        # Remove duplicates while preserving first-seen casing/order.
        deduped = []
        seen = set()
        for name in existing_names:
            key = name.lower()
            if key not in seen:
                deduped.append(name)
                seen.add(key)

        new_block = []
        for name in deduped:
            new_block.append(f"/addon load {name}")

        # Keep any unusual non-empty lines in the block rather than deleting user data.
        if other_lines:
            if new_block:
                new_block.append("")
            new_block.extend(other_lines)

        self.default_script.parent.mkdir(parents=True, exist_ok=True)
        self.default_script.write_text("\n".join(before + new_block + after) + "\n", encoding="utf-8")

    def _find_main_lua(self, folder):
        preferred = folder / f"{folder.name}.lua"
        if preferred.exists():
            return preferred

        direct_luas = sorted(folder.glob("*.lua"), key=lambda p: p.name.lower())
        if direct_luas:
            return direct_luas[0]

        nested_luas = sorted(folder.rglob("*.lua"), key=lambda p: str(p).lower())
        return nested_luas[0] if nested_luas else None

    def _read_addon_name(self, lua_path):
        try:
            text = lua_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

        # Common Ashita v4 format: addon.name = 'targetlines';
        match = re.search(
            r"addon\.name\s*=\s*['\"]([^'\"]+)['\"]",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

        return None

    def _read_addon_description(self, lua_path):
        try:
            text = lua_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

        # Common Ashita v4 format: addon.desc = 'description';
        match = re.search(
            r"addon\.desc\s*=\s*['\"]([^'\"]*)['\"]",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            return " ".join(match.group(1).strip().split())

        return None

    def _read_lines(self):
        if not self.default_script.exists():
            return []
        return self.default_script.read_text(encoding="utf-8", errors="ignore").splitlines()

    def _find_block(self, lines):
        start = None
        stop = None

        for index, line in enumerate(lines):
            if line.strip() == ADDONS_START:
                start = index
            elif line.strip() == ADDONS_STOP and start is not None:
                stop = index
                break

        return start, stop

    def _append_addon_block(self, lines):
        if lines and lines[-1].strip():
            lines.append("")

        lines.extend(
            [
                "##########################################################################",
                "#",
                "# Horizon Launcher Controlled Addons",
                "#",
                "##########################################################################",
                ADDONS_START,
                ADDONS_STOP,
                "",
            ]
        )
        return lines
