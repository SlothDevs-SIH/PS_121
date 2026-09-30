"""Login, users and the audit log (B5)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import ResponseModel
from app.core.auth import Role


class Me(ResponseModel):
    user_id: str
    name: str
    roles: list[Role]
    permissions: list[str] = Field(description="What the roles allow; the UI hides the rest")
    auth_mode: str


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class TokenOut(ResponseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (the OAuth2 token type, not a secret)
    expires_at: datetime
    user: Me


class UserOut(ResponseModel):
    id: int
    username: str
    name: str
    roles: list[Role]
    active: bool
    created_at: datetime
    last_login_at: datetime | None
    locked_until: datetime | None


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9._-]+$")
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=200)
    roles: list[Role] = Field(min_length=1)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    password: str | None = Field(None, min_length=12, max_length=200)
    roles: list[Role] | None = Field(None, min_length=1)
    active: bool | None = None
    unlock: bool = Field(False, description="Clear a lockout after failed logins")
    revoke_sessions: bool = Field(False, description="End every session of this user now")


class AuditEntry(ResponseModel):
    id: int
    at: datetime
    user_id: str
    action: str
    target_type: str | None
    target_id: str | None
    detail: dict[str, Any]
    request_id: str | None


class AuditPage(ResponseModel):
    items: list[AuditEntry]
    next_before_id: int | None = Field(description="Pass as before_id for the next (older) page")


class OidcConfig(ResponseModel):
    issuer: str = Field(description="Issuer URL as the browser reaches it")
    client_id: str
    authorize_url: str = Field(description="Where the browser starts the PKCE login")
    end_session_url: str | None = Field(description="The provider's logout page, if any")


class OidcCallbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=4096)
    code_verifier: str = Field(min_length=43, max_length=128)  # RFC 7636
    redirect_uri: str = Field(min_length=1, max_length=2048)


class SessionOut(ResponseModel):
    """A browser session was set in HttpOnly cookies; no token in the body."""

    user: Me
    expires_at: datetime


class AuthConfig(ResponseModel):
    """What the login screen needs before anyone is logged in (public)."""

    auth_mode: str
    oidc: OidcConfig | None
    session_max_hours: int
