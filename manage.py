from __future__ import annotations

import importlib.util
from pathlib import Path


_APP_PATH = Path(__file__).resolve().with_name("app.py")
_SPEC = importlib.util.spec_from_file_location("gameswitch_entry", _APP_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Flask app entry module")

_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

app = _MODULE.app
