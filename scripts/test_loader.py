from pathlib import Path
import sys

# Add the src directory to Python's module search path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

from proton.proton_manager import ProtonManager
from launcher.horizon_manager import HorizonManager
from launcher.launcher import Launcher

launcher = Launcher(
    ProtonManager(),
    HorizonManager(),
)

launcher.launch_game_direct(
    "YOUR_USERNAME",
    "YOUR_PASSWORD",
)
