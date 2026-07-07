import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_key(request):
    """Rate-limit key for the request.

    Defaults to the raw socket IP. If TRUST_PROXY_HEADERS=1 is set (only do
    this when the app sits behind a reverse proxy you control that always
    overwrites X-Forwarded-For itself), the first hop of X-Forwarded-For is
    used instead — otherwise every user behind an untrusted proxy collapses
    into one shared bucket, and one busy user can 429 everyone else.
    """
    if os.environ.get("TRUST_PROXY_HEADERS") == "1":
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_key)
