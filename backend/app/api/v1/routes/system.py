"""Implemented in B0: service metadata, build status and the current user."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import __version__
from app.api.v1.schemas.auth import LoginIn, Me, TokenOut
from app.core import users
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.phases import COMPONENTS, CURRENT_PHASE, Component
from app.db.session import get_session

router = APIRouter(tags=["system"])


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


@router.post(
    "/auth/login",
    response_model=TokenOut,
    summary="Log in (jwt auth mode): a bearer token for one shift",
    responses={401: {"description": "Wrong username or password"}},
)
def login(
    body: Annotated[LoginIn, Body()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenOut:
    out = users.login(session, settings, body.username, body.password)
    session.commit()
    return out
