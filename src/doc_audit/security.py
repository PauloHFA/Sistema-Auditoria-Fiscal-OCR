import secrets

from fastapi import Header, HTTPException, status

from doc_audit.config import settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key ausente ou inválida",
            headers={"WWW-Authenticate": "ApiKey"},
        )
