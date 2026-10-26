"""Temporary OG crawler diagnostics for debug mode (session 0784a2)."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

# #region agent log
_HITS: deque[dict] = deque(maxlen=80)
_LOG_PATH = Path("/home/biga/git/bigazzzz/rashod/.cursor/debug-0784a2.log")
_FALLBACK_LOG = Path("/tmp/rashod-debug-0784a2.log")


def agent_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
    run_id: str = "prod",
) -> None:
    entry = {
        "sessionId": "0784a2",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    _HITS.append(entry)
    for path in (_LOG_PATH, _FALLBACK_LOG):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            break
        except OSError:
            continue


def recent_hits() -> list[dict]:
    return list(_HITS)


# #endregion
