import json
from pathlib import Path

from app import __version__

VERSIONS_PATH = Path(__file__).parent / "static" / "versions.json"


def load_releases(limit: int | None = 3) -> list[dict]:
    raw = VERSIONS_PATH.read_text(encoding="utf-8")
    releases = json.loads(raw)
    if not isinstance(releases, list):
        raise ValueError("versions.json must be a JSON array")
    if limit is None:
        return releases
    return releases[:limit]


def current_version() -> str:
    return __version__
