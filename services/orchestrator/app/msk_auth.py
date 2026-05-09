"""
MSK IAM SASL auth helper for aiokafka.

aiokafka supports SASL/OAUTHBEARER, which we use as the carrier for an
AWS SigV4 token produced by aws-msk-iam-sasl-signer-python.

Falls back to plaintext (for local docker-compose) when MSK_USE_IAM is false.
"""
from __future__ import annotations

import logging
import ssl
from typing import Any, Optional

logger = logging.getLogger(__name__)


def kafka_client_kwargs(
    *, brokers: str, region: str, use_iam: bool
) -> dict[str, Any]:
    """Return aiokafka client kwargs: bootstrap_servers + auth config."""
    if not use_iam:
        return {"bootstrap_servers": brokers}

    try:
        from aws_msk_iam_sasl_signer import MSKAuthTokenProvider
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "aws-msk-iam-sasl-signer-python not installed; "
            "set MSK_USE_IAM=false for local dev or install the package"
        ) from e

    ssl_ctx = ssl.create_default_context()

    async def token_provider() -> tuple[str, int]:
        token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(region)
        return token, int(expiry_ms)

    return {
        "bootstrap_servers": brokers,
        "security_protocol": "SASL_SSL",
        "sasl_mechanism": "OAUTHBEARER",
        "sasl_oauth_token_provider": _AsyncTokenProvider(token_provider),
        "ssl_context": ssl_ctx,
    }


class _AsyncTokenProvider:
    """Adapter so aiokafka receives an object with .token() returning a coroutine."""

    def __init__(self, fetcher) -> None:
        self._fetcher = fetcher

    async def token(self) -> str:
        token, _expiry = await self._fetcher()
        return token
