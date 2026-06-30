#!/usr/bin/env python3

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from proton.proton_manager import ProtonManager


proton = ProtonManager()
proton.install()

print("Installed:", proton.is_installed())
print("Path:", proton.get_path())
