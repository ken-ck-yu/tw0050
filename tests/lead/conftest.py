"""Make sibling helper modules (fixtures_inline) importable under --import-mode=importlib."""

import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
