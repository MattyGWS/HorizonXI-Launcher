#!/usr/bin/env python3

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diagnostics import print_startup_diagnostics
from ui.window import HorizonWindow


def main():
    print_startup_diagnostics()
    app = HorizonWindow()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
