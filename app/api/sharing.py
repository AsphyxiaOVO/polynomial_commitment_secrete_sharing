from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.sharing import CreateSharingRequest, OwnShareOut, SharingTaskOut
from app.security.authorization import Actor
from app.services.sharing_service import SharingService
from app.storage.repository import Repository

from .deps import get_current_actor, get_repository, require_dealer_for_creation

router = APIRouter(prefix="/api/v1/sharing", tags=["sharing"])


@router.post("", response_model=SharingTaskOut, status_code=status.HTTP_201_CREATED,
             summary="Create a sharing task (dealer only)")
def create_sharing(body: CreateSharingRequest,
                   actor: Actor = Depends(require_dealer_for_creation),
                   repo: Repository = Depends(get_repository)) -> SharingTaskOut:
    view = SharingService(repo).create(actor, body.message, body.threshold, body.participant_ids)
    return SharingTaskOut.from_view(view)


@router.get("/{sharing_id}", response_model=SharingTaskOut,
            summary="Public task metadata (task dealer or recipients)")
def get_sharing(sharing_id: str, actor: Actor = Depends(get_current_actor),
                repo: Repository = Depends(get_repository)) -> SharingTaskOut:
    return SharingTaskOut.from_view(SharingService(repo).get(actor, sharing_id))


@router.post("/{sharing_id}/distribute", response_model=SharingTaskOut,
             summary="Distribute shares (task dealer only; second call -> 409)")
def distribute(sharing_id: str, actor: Actor = Depends(get_current_actor),
               repo: Repository = Depends(get_repository)) -> SharingTaskOut:
    return SharingTaskOut.from_view(SharingService(repo).distribute(actor, sharing_id))


@router.get("/{sharing_id}/shares/me", response_model=OwnShareOut,
            summary="The caller's own share (recipients only)")
def my_share(sharing_id: str, actor: Actor = Depends(get_current_actor),
             repo: Repository = Depends(get_repository)) -> OwnShareOut:
    return OwnShareOut.from_view(SharingService(repo).get_own_share(actor, sharing_id))
