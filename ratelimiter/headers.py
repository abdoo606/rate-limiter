"""HTTP header conventions (RFC 9331 style) so clients can back off politely."""

from __future__ import annotations

import math

from .algorithms import Decision

STANDARD = "X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"


def headers_for(decision: Decision) -> dict[str, str]:
    headers = {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(max(0, decision.remaining)),
    }
    if not decision.allowed:
        retry = max(1, math.ceil(decision.retry_after))
        headers["Retry-After"] = str(retry)
    return headers


def status_for(decision: Decision) -> int:
    return 200 if decision.allowed else 429
