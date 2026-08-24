"""Bounded retry with exponential backoff for off-chain transport calls.

Retries transient failures only: httpx transport errors (connect/read/etc.)
and 5xx responses. 4xx responses are returned immediately — they are the
caller's problem, not a transient fault. Publishes are safe to retry because
the off-chain request handler de-duplicates by requestId.
"""

import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 0.25
DEFAULT_MAX_DELAY_S = 2.0


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
    **kwargs,
) -> httpx.Response:
    """Issue an HTTP request, retrying transport errors and 5xx responses.

    Backoff between attempts: ``base * 2^n`` with ±25% jitter, capped at
    ``max_delay_s``. The final attempt's response is returned (or its
    exception raised) unmodified, so callers keep their normal error handling.
    """
    last_exc: httpx.TransportError | None = None
    for attempt in range(attempts):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
            logger.warning(
                "Transport error on %s %s (attempt %d/%d): %s — retrying",
                method,
                url,
                attempt + 1,
                attempts,
                exc,
            )
        else:
            if response.status_code not in RETRYABLE_STATUS or attempt == attempts - 1:
                return response
            logger.warning(
                "HTTP %d on %s %s (attempt %d/%d) — retrying",
                response.status_code,
                method,
                url,
                attempt + 1,
                attempts,
            )

        delay = min(base_delay_s * (2**attempt), max_delay_s)
        await asyncio.sleep(delay * random.uniform(0.75, 1.25))

    raise last_exc if last_exc else RuntimeError("retry loop exited unexpectedly")
