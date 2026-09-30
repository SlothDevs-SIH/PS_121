"""Implemented in B0: service metadata, build status and the current user."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import __version__
from app.api.v1.schemas.auth import (
    AuthConfig,
    LoginIn,
    Me,
    OidcCallbackIn,
    OidcConfig,
    SessionOut,
    TokenOut,
)
from app.core import oidc as oidc_core
from app.core import ratelimit, users
from app.core.audit import audit
from app.core.auth import (
    CurrentUser,
    get_current_user,
    token_from_request,
    user_for_token,
    user_id_from_token,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.phases import COMPONENTS, CURRENT_PHASE, Component
from app.db.models.auth import AppUser
from app.db.session import get_session

router = APIRouter(tags=["system"])
REFRESH_COOKIE = "smriti_refresh"
REFRESH_PATH = "/api/v1/auth"  # the refresh token is only ever sent to the auth routes


class Meta(BaseModel):
    name: str
    version: str
    git_sha: str
    env: str
    backend_phase: str
    components: list[Component]


@router.get("/meta", response_model=Meta, summary="Service metadata and component build status")
def meta(settings: Annotated[Settings, Depends(get_settings)]) -> Meta:
    return Meta(
        name="SMRITI backend (eRTMAC-NWIS, SIH PS 121)",
        version=__version__,
        git_sha=settings.git_sha,
        env=settings.env,
        backend_phase=CURRENT_PHASE,
        components=COMPONENTS,
    )


@router.get("/me", response_model=Me, summary="The authenticated user and what they may do")
def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Me:
    return users.me(user, settings)


def _client_ip(request: Request, settings: Settings) -> str:
    # Behind our nginx (which overwrites X-Real-IP) the header is the client; otherwise it
    # could be forged, so only the TCP peer counts.
    peer = request.client.host if request.client else "?"
    if settings.trust_proxy_headers:
        return request.headers.get("x-real-ip") or peer
    return peer


def _set_session(response: Response, settings: Settings, out: TokenOut) -> None:
    max_age = max(0, int((out.expires_at - datetime.now(tz=UTC)).total_seconds()))
    response.set_cookie(
        settings.session_cookie_name,
        out.access_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.get(
    "/auth/config",
    response_model=AuthConfig,
    summary="Auth mode and (OIDC) provider details for the login screen; public",
)
def auth_config(settings: Annotated[Settings, Depends(get_settings)]) -> AuthConfig:
    oidc = None
    if settings.auth_mode == "oidc" and settings.oidc_issuer:
        oidc = OidcConfig(
            issuer=settings.oidc_public_issuer or settings.oidc_issuer,
            client_id=settings.oidc_client_id,
            authorize_url=oidc_core.authorize_url(settings) or "",
            end_session_url=oidc_core.end_session_url(settings),
        )
    return AuthConfig(
        auth_mode=settings.auth_mode, oidc=oidc, session_max_hours=settings.session_max_hours
    )


@router.post(
    "/auth/login",
    response_model=TokenOut,
    summary="Log in (jwt mode): sets the HttpOnly session cookie and returns the token",
    responses={
        401: {"description": "Wrong username or password (or a locked account)"},
        429: {"description": "Too many login attempts from this address"},
    },
)
def login(
    body: Annotated[LoginIn, Body()],
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenOut:
    ratelimit.hit(f"login:{_client_ip(request, settings)}", settings.login_rate_per_minute)
    out = users.login(session, settings, body.username, body.password)
    session.commit()
    _set_session(response, settings, out)
    return out


@router.post(
    "/auth/refresh",
    response_model=TokenOut | SessionOut,
    summary="Renew the session (jwt: up to session_max_hours after login; oidc: at the IdP)",
)
def refresh(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenOut | SessionOut:
    if settings.auth_mode == "oidc":
        tokens = users.oidc_refresh(settings, request.cookies.get(REFRESH_COOKIE))
        return _set_oidc_session(response, session, settings, tokens, "session_refresh")
    token, _ = token_from_request(request, settings)
    out = users.refresh(session, settings, token)
    _set_session(response, settings, out)
    return out


@router.post(
    "/auth/logout",
    status_code=204,
    summary="End this browser's session (clears the cookie)",
)
def logout(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    token, _ = token_from_request(request, settings)
    if token and settings.auth_mode == "jwt":
        try:
            u = session.get(AppUser, user_id_from_token(settings, token))
            if u is not None:
                audit(session, u.username, "logout", "user", u.id)
                session.commit()
        except AppError:
            pass  # an expired or invalid token still gets its cookie cleared
    out = Response(status_code=204)
    out.delete_cookie(settings.session_cookie_name, path="/", samesite="strict")
    out.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, samesite="strict")
    return out


@router.post(
    "/auth/oidc/callback",
    response_model=SessionOut,
    summary="Finish an OIDC login: exchange the code (PKCE) and set the session cookies",
    responses={401: {"description": "The provider refused the code, or the token is invalid"}},
)
def oidc_callback(
    body: Annotated[OidcCallbackIn, Body()],
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionOut:
    """The browser never holds the tokens: this server trades the code at the provider's
    token endpoint and keeps the access token (and the refresh token, on the auth path
    only) in HttpOnly, SameSite=Strict cookies."""
    ratelimit.hit(f"login:{_client_ip(request, settings)}", settings.login_rate_per_minute)
    tokens = users.oidc_exchange(settings, body.code, body.code_verifier, body.redirect_uri)
    return _set_oidc_session(response, session, settings, tokens, "login")


def _set_oidc_session(
    response: Response,
    session: Session,
    settings: Settings,
    tokens: dict[str, Any],
    action: str,
) -> SessionOut:
    user = user_for_token(settings, session, tokens.get("access_token"))
    audit(session, user, action, "user", user.user_id, via="oidc")
    session.commit()
    ttl = int(tokens.get("expires_in") or 300)
    response.set_cookie(
        settings.session_cookie_name,
        tokens["access_token"],
        max_age=ttl,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    if tokens.get("refresh_token"):
        response.set_cookie(
            REFRESH_COOKIE,
            tokens["refresh_token"],
            max_age=int(tokens.get("refresh_expires_in") or 1800),
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            path=REFRESH_PATH,
        )
    return SessionOut(
        user=users.me(user, settings), expires_at=datetime.now(tz=UTC) + timedelta(seconds=ttl)
    )
