"""Authentication/authorisation.

B0: ``SMRITI_AUTH_MODE=dev`` returns a fixed local admin so endpoints can be exercised.
B6: ``oidc`` validates Keycloak bearer tokens and maps realm roles (master plan §16).
"""

from typing import Annotated, Literal

from fastapi import Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.errors import AppError

Role = Literal[
    "viewer", "field_engineer", "rtmac_engineer", "drilling_engineer", "data_steward", "admin"
]


class CurrentUser(BaseModel):
    user_id: str
    name: str
    roles: list[Role]


class AuthNotConfiguredError(AppError):
    status_code = 503
    code = "auth_not_configured"


def get_current_user(settings: Annotated[Settings, Depends(get_settings)]) -> CurrentUser:
    if settings.auth_mode == "dev":
        if settings.env == "prod":
            raise AuthNotConfiguredError("Dev auth mode is refused when SMRITI_ENV=prod.")
        return CurrentUser(user_id="dev", name="Local Developer", roles=["admin"])
    raise AuthNotConfiguredError("OIDC authentication is planned for backend phase B6.")
