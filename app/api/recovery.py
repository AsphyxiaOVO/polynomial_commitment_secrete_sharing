from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.recovery import RecoverRequest, RecoverResponse
from app.security.authorization import Actor
from app.services.recovery_service import RecoveryService
from app.storage.repository import Repository

from .deps import get_current_actor, get_repository

router = APIRouter(prefix="/api/v1/sharing", tags=["recovery"])


@router.post("/{sharing_id}/recover", response_model=RecoverResponse,
             summary="Recover the secret from >= k submitted shares (task dealer or recipients)")
def recover(sharing_id: str, body: RecoverRequest, actor: Actor = Depends(get_current_actor),
            repo: Repository = Depends(get_repository)) -> RecoverResponse:
    submitted = [(s.x, [int(v) for v in s.values]) for s in body.shares]
    outcome = RecoveryService(repo).recover(actor, sharing_id, submitted)
    return RecoverResponse(sharing_id=outcome.sharing_id, message=outcome.message,
                           shares_used=outcome.shares_used, threshold=outcome.threshold)
