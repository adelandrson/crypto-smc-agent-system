"""Tool handlers for the indicators plugin. Return JSON string; never raise."""

import json

try:
    from .ind import engine as _engine
except ImportError:
    from ind import engine as _engine


def ind_analyze(args: dict, **kwargs) -> str:
    del kwargs
    try:
        bars = args.get("bars")
        if not bars:
            return json.dumps({"ok": False, "error": "provide 'bars' (OHLC array)"})
        res = _engine.analyze(bars, args.get("config") or {})
        return json.dumps(res)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})
