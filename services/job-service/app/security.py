from hmac import compare_digest

from fastapi import Header, HTTPException, status

from app.config import get_settings

settings = get_settings()


def _require_token(
    provided: str | None,
    expected: str,
    detail: str,
) -> None:
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured",
        )
    if not provided or not compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    _require_token(x_api_key, settings.api_key, "Invalid API key")


async def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    _require_token(
        x_internal_token,
        settings.internal_api_token,
        "Invalid internal service token",
    )
