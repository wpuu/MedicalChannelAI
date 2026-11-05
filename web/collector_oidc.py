from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def preview_oidc_token() -> str | None:
    """Resolve the current platform token without CLI refresh or network calls.

    The public synchronous SDK lookup handles request-header context, rotated
    token-file credentials and environment credentials. Do not cache tokens here
    or log SDK exceptions, which can include credential-bearing details.
    Callers must validate the exact Preview self-host before using this value.
    """
    if str(os.environ.get("VERCEL_ENV") or "").strip().lower() != "preview":
        return None
    try:
        from vercel.oidc import get_vercel_oidc_token_sync
    except ImportError:
        # Preserve standalone/local compatibility where the runtime SDK is absent.
        token = str(os.environ.get("VERCEL_OIDC_TOKEN") or "").strip()
        if not token:
            logger.warning("preview_oidc_lookup reason=SDK_UNAVAILABLE")
        return token or None
    try:
        token = get_vercel_oidc_token_sync()
    except Exception:
        logger.warning("preview_oidc_lookup reason=SDK_TOKEN_UNAVAILABLE")
        return None
    if not isinstance(token, str):
        return None
    return token.strip() or None
