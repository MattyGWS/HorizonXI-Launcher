#!/usr/bin/env python3

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from launcher.horizon_manager import HorizonManager


horizon = HorizonManager()
horizon.ensure_dirs()

print("Launcher path:")
print(horizon.get_launcher_path())
print()
print("Installed:", horizon.is_installed())
