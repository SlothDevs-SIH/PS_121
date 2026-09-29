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
