"""Implemented in B0: service metadata, build status and the current user."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.phases import COMPONENTS, CURRENT_PHASE, Component

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


@router.get("/me", response_model=CurrentUser, summary="The authenticated user")
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    return user
