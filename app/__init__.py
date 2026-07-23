from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_entrypoint_app():
    entrypoint_path = Path(__file__).resolve().parent.parent / "app.py"
    spec = importlib.util.spec_from_file_location("_gameswitch_app_entrypoint", entrypoint_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "app", None)


app = _load_entrypoint_app()

__all__ = ["app"]
