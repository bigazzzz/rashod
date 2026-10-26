# #region agent log
import json
import time
from collections import deque

_HITS: deque = deque(maxlen=150)


def agent_log(*, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    entry = {"sessionId": "0784a2", "runId": "vk-wall", "hypothesisId": hypothesis_id, "location": location, "message": message, "data": data, "timestamp": int(time.time() * 1000)}
    _HITS.append(entry)
    try:
        with open("/tmp/rashod-debug-0784a2.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent_hits() -> list[dict]:
    return list(_HITS)
# #endregion
