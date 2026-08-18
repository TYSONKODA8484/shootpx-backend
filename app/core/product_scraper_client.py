"""Thin HTTP client for the product-scrapper service (separate repo,
separate process — see PRODUCT_SCRAPER_URL, core/config.py). Deliberately
the same submit()/poll() shape as AIProvider (core/ai_provider.py): one
fast HTTP call each, never a blocking wait — the service's own /extract
can take 2-25s internally, but that happens on its side, not ours.

Not an AIProvider itself (doesn't produce a GenerationResult — a product
import's output is several images plus structured data, a different shape
entirely, see models/product_import.py) — a separate, parallel client
with the same pattern for the same reason.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings


@dataclass
class ScrapeHandle:
    external_job_id: str


class ScrapePending(Exception):
    """Raised by poll() when the scraper service hasn't finished yet —
    not an error, app/worker.py requeues via arq's Retry, same as
    GenerationPending in core/ai_provider.py."""


def submit(url: str) -> ScrapeHandle:
    resp = httpx.post(
        f"{settings.PRODUCT_SCRAPER_URL}/extract",
        json={"url": url},
        timeout=10.0,  # this call, not the scrape itself — submit only
        # waits for the service to accept the job and hand back an id
    )
    resp.raise_for_status()
    return ScrapeHandle(external_job_id=resp.json()["id"])


def poll(handle: ScrapeHandle) -> dict[str, Any]:
    """Returns the scraper's raw ExtractionResult dict once done. Raises
    ScrapePending if the service reports status "pending"."""
    resp = httpx.get(
        f"{settings.PRODUCT_SCRAPER_URL}/extract/{handle.external_job_id}",
        timeout=10.0,
    )
    resp.raise_for_status()
    body = resp.json()
    if body["status"] == "pending":
        raise ScrapePending()
    return body["result"]
