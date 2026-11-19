from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, status

from app.schemas.verification import (DealerVerifyResponse, ParticipantVerifyResponse, ProofOut,
                                      ProofRequest, VerificationDetails, VerifyRequest)
from app.security.authorization import Actor
from app.services.verification_service import InlineProof, VerificationService
from app.storage.repository import Repository

from .deps import get_current_actor, get_repository

router = APIRouter(prefix="/api/v1/sharing", tags=["proofs"])


@router.post("/{sharing_id}/proofs", response_model=ProofOut, status_code=status.HTTP_201_CREATED,
             summary="Generate an evaluation-consistency proof for one recipient (task dealer only)")
def generate_proof(sharing_id: str, body: ProofRequest, actor: Actor = Depends(get_current_actor),
                   repo: Repository = Depends(get_repository)) -> ProofOut:
    challenge = int(body.challenge) if body.challenge is not None else None
    view = VerificationService(repo).generate_proof(actor, sharing_id, body.participant_id, challenge)
    return ProofOut.from_view(view)


@router.post("/{sharing_id}/verify",
             response_model=Union[DealerVerifyResponse, ParticipantVerifyResponse],
             summary="Verify a proof (task dealer or recipients); failure -> 200 verified=false")
def verify(sharing_id: str, body: VerifyRequest, actor: Actor = Depends(get_current_actor),
           repo: Repository = Depends(get_repository)
           ) -> Union[DealerVerifyResponse, ParticipantVerifyResponse]:
    inline = None
    if body.proof is not None:
        p = body.proof
        inline = InlineProof(x=p.x, challenge=int(p.challenge),
                             commitments=[int(c) for c in p.commitments], witness=int(p.witness))
    outcome = VerificationService(repo).verify(actor, sharing_id, proof_id=body.proof_id, proof=inline)
    if outcome.caller_is_task_dealer:
        return DealerVerifyResponse(verified=outcome.verified, details=VerificationDetails(
            left_value=str(outcome.left_value), right_value=str(outcome.right_value)))
    return ParticipantVerifyResponse(
        verified=outcome.verified,
        message="Verification successful" if outcome.verified else "Verification failed")
