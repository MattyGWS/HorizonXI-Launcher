#!/usr/bin/env python3

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from proton.proton_manager import ProtonManager


proton = ProtonManager()
proton.ensure_dirs()

print("Expected Proton version:", proton.VERSION)
print("Expected Proton path:", proton.get_path())
print("Installed:", proton.is_installed())
