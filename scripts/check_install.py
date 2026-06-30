#!/usr/bin/env python3

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from install.install import InstallManager


def progress(message):
    print("[installer]", message)


installer = InstallManager()

print("Installed before:", installer.is_installed())

installer.install(progress)

print("Installed after:", installer.is_installed())
