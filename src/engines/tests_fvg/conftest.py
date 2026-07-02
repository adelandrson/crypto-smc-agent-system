"""Test bootstrap.

The plugin root contains a Hermes-facing ``__init__.py`` (with package-relative
imports). To test the engine in isolation we load the ``fvg`` sub-package
directly via importlib — without putting the plugin root on ``sys.path`` — so
pytest never tries to import that root package.
"""

import importlib.util
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_root = _here.parents[1]

if "fvg" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "fvg",
        _root / "fvg" / "__init__.py",
        submodule_search_locations=[str(_root / "fvg")],
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["fvg"] = _mod
    _spec.loader.exec_module(_mod)

# Allow sibling helper imports (`import fixtures`).
_tests = str(_here.parent)
if _tests not in sys.path:
    sys.path.insert(0, _tests)
