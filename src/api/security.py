from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_environment: str = "development"
    jwt_secret: str = "local-only-secret-key-change-this-value-123456"
    jwt_issuer: str = "ic-ai-assist-local"
    jwt_audience: str = "ic-ai-assist-api"
    jwt_expiration_minutes: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

settings = Settings()
bearer_scheme = HTTPBearer(auto_error=False)

class AuthUser(BaseModel):
    user_id: str
    tenant_id: str
    role: str

def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(
        minutes=settings.jwt_expiration_minutes
    )

    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm="HS256",
    )

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> AuthUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        role = payload.get("role")

        if not user_id or not tenant_id or not role:
            raise ValueError("Required claims are missing.")

        return AuthUser(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
        )

    except (jwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is invalid or expired.",
        ) from exc

def require_roles(*allowed_roles: str) -> Callable:
    def dependency(
        user: AuthUser = Depends(get_current_user),
    ) -> AuthUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The user is not authorized for this operation.",
            )

        return user

    return dependency

read_access = require_roles(
    "viewer",
    "investigator",
    "reviewer",
    "admin",
)

feedback_access = require_roles(
    "investigator",
    "reviewer",
    "admin",
)
