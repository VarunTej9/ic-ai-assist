from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
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

class CurrentUser(BaseModel):
    user_id: str
    tenant_id: str
    role: str

def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(
            minutes=settings.jwt_expiration_minutes
        ),
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
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=401,
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

        return CurrentUser(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            role=payload["role"],
        )
    except (jwt.InvalidTokenError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="The access token is invalid or expired.",
        )

def require_roles(*roles: str) -> Callable:
    def check_role(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="The user is not authorized for this operation.",
            )
        return user

    return check_role

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
