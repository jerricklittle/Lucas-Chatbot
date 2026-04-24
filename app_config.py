"""Centralized public URL and research-site configuration (env-driven)."""

import os
from typing import Optional

from starlette.requests import Request


def get_public_base_url(request: Optional[Request] = None) -> str:
    """
    Canonical base URL for link generation (IR CSV) and OAuth redirects.

    Priority:
    1. ``PUBLIC_BASE_URL`` — use in production (e.g. Railway) for correct https:// host.
    2. ``RAILWAY_PUBLIC_DOMAIN`` — https://{domain} when the public domain env is set.
    3. Local / non-Railway: if ``request`` is provided and ``RAILWAY_ENVIRONMENT`` is not set
       (typical ``nicegui`` / ``uvicorn`` on your laptop), derive from ``request.base_url``
       so you get ``http://localhost:8080`` or ``http://10.x.x.x:8080`` without extra env.

    On Railway, ``RAILWAY_ENVIRONMENT`` is set, so step 3 is skipped unless you also set
    ``PUBLIC_BASE_URL`` / ``RAILWAY_PUBLIC_DOMAIN`` — which you should for stable links.
    """
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base:
        return base
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if domain:
        return f"https://{domain}"
    if request is not None and not os.getenv("RAILWAY_ENVIRONMENT", "").strip():
        return str(request.base_url).rstrip("/")
    return ""


def get_informed_consent_url() -> str:
    """Optional external URL for the full informed consent document."""
    return os.getenv("INFORMED_CONSENT_URL", "").strip()


def parse_email_set(env_name: str) -> set[str]:
    raw = os.getenv(env_name, "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}
