"""Authentication guard for the private GoCity administration API."""

from __future__ import annotations

import hmac
import logging
import os
from typing import Annotated

from fastapi import Header, HTTPException, status


LOGGER = logging.getLogger("gocity.admin_security")


def require_admin_api_key(
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Require the server-to-server key used by the admin-console proxy.

    There is deliberately no development default. A missing key must leave
    sensitive admin data unavailable instead of silently publishing it.
    """
    configured_key = os.getenv("ADMIN_API_KEY")
    if not configured_key:
        LOGGER.critical("admin_api_disabled reason=ADMIN_API_KEY_not_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured.",
        )

    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, configured_key):
        LOGGER.warning("admin_api_rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
            headers={"WWW-Authenticate": "AdminApiKey"},
        )
