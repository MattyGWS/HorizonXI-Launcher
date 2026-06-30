"""HorizonXI game install/update API endpoints.

The official HorizonXI launcher obtains game download data from these API
endpoints. We use the same flow instead of hardcoding base/patch magnets.
"""

PREREQS_ARCHIVE = {
    "name": "prereqs.zip",
    "url": "https://github.com/HorizonFFXI/Launcher-Prereqs/archive/refs/heads/main.zip",
}

LAUNCHER_API_BASE = "https://api.horizonxi.com/api/v1/launcher"

INSTALL_GAME_URL = f"{LAUNCHER_API_BASE}/install-game"
UPDATE_GAME_URL = f"{LAUNCHER_API_BASE}/update-game"
LATEST_VERSION_URL = f"{LAUNCHER_API_BASE}/latest-version"

# Kept only as a defensive fallback if the API shape changes temporarily.
LATEST_GAME_VERSION = None
