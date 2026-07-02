"""Load the sfib sub-package directly (plugin root has a Hermes __init__.py)."""
import importlib.util
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_root = _here.parents[1]

if "sfib" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "sfib", _root / "sfib" / "__init__.py",
        submodule_search_locations=[str(_root / "sfib")])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sfib"] = mod
    spec.loader.exec_module(mod)

if str(_here.parent) not in sys.path:
    sys.path.insert(0, str(_here.parent))
