"""Response outcome classification for buyer benchmark runs.

Six terminal outcomes (spec 4.1 / 10.1):
  ok | empty_valid | empty_suspect | blocked | transient_error | invalid

Classification uses ONLY the HTTP status, content-type, parsed body and the
expected widget kind -- never authenticated headers or cookies. 3xx is a normal
search-page redirect and is NOT a rejection.
"""
from __future__ import annotations

from typing import Any, Dict

# Expected widget name fragments per kind (Kit widgetStates keys).
_WIDGET_MARKERS = {
    "inventory": ("searchResultsV2", "tileGrid"),
    "reviews": ("webListReviews",),
}


def _widget_present(body: Any, kind: str) -> bool:
    if not isinstance(body, dict):
        return False
    ws = body.get("widgetStates", {})
    if not isinstance(ws, dict):
        return False
    markers = _WIDGET_MARKERS.get(kind, ())
    return any(any(mk in key for mk in markers) for key in ws)


def _record_count(body: Any, kind: str) -> int:
    if not isinstance(body, dict):
        return 0
    ws = body.get("widgetStates", {})
    markers = _WIDGET_MARKERS.get(kind, ())
    import json as _json
    for key, raw in ws.items():
        if not any(mk in key for mk in markers):
            continue
        try:
            val = _json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if not isinstance(val, dict):
            continue
        if kind == "inventory":
            items = val.get("items") or []
            if items:
                return len(items)
        else:
            total = (val.get("paging") or {}).get("total")
            revs = val.get("reviews") or []
            if total or revs:
                return len(revs) or (total or 0)
    return 0


def classify_buyer_response(
    status_code: int,
    content_type: str,
    body: Any,
    kind: str,
) -> str:
    """Return one of the six outcome strings.

    body is the already-parsed envelope (dict) or a raw string. A 200 that
    carries no expected widget is ``empty_suspect`` -- never silently success.
    """
    ct = (content_type or "").lower()
    text = body if isinstance(body, str) else (json_snippet(body) or "")
    low = text[:512].lower()

    # Access restrictions -> blocked (never empty stock, never same-ticket retry)
    if status_code in (401, 403, 429):
        return "blocked"
    # HTML antibot/challenge page even on a 200
    if "text/html" in ct and ("antibot" in low or "challenge" in low):
        return "blocked"

    # Transient server-side problems
    if status_code >= 500 or status_code in (408, 425):
        return "transient_error"

    # 404 / non-JSON / unparseable -> invalid
    if status_code == 404 or not isinstance(body, dict):
        return "invalid"

    if status_code != 200:
        return "invalid"

    # 200: decide between ok / empty_valid / empty_suspect
    if not _widget_present(body, kind):
        return "empty_suspect"
    n = _record_count(body, kind)
    if n > 0:
        return "ok"
    # widget present but explicitly zero records
    return "empty_valid"


def json_snippet(body: Any) -> str:
    try:
        import json as _j
        return _j.dumps(body, ensure_ascii=False)
    except Exception:
        return ""
