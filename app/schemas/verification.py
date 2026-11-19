from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, StrictInt, model_validator

from pcss.config import MAX_CHUNK_COUNT

from .common import DecimalStr, PublicParametersOut, StrictModel, to_str_list

VERIFICATION_EQUATION = "W * Z_T(x) == sum_i (cm_i - r_i(x)) * y^i * Z_{T\\S_i}(x)  (mod p)"


class ProofRequest(StrictModel):
    participant_id: str = Field(min_length=1, max_length=64,
                                description="Recipient whose share coordinate x is opened")
    challenge: Optional[DecimalStr] = Field(
        default=None, description="Challenge y in [1, p-1]; drawn with `secrets` when omitted")


class ProofOut(BaseModel):
    proof_id: str
    sharing_id: str
    participant_id: str
    x: int
    challenge: str
    commitments: List[str] = Field(description="cm_i = f_i(x); equal to the recipient's share values")
    witness: str
    public_parameters: PublicParametersOut
    verification_equation: str = VERIFICATION_EQUATION
    created_at: datetime

    @classmethod
    def from_view(cls, v) -> "ProofOut":
        return cls(proof_id=v.proof_id, sharing_id=v.sharing_id, participant_id=v.participant_id,
                   x=v.x, challenge=str(v.challenge), commitments=to_str_list(v.commitments),
                   witness=str(v.witness),
                   public_parameters=PublicParametersOut(
                       point_sets=[to_str_list(s) for s in v.point_sets],
                       evaluation_set=to_str_list(v.evaluation_set)),
                   created_at=v.created_at)


class InlineProofIn(StrictModel):
    x: StrictInt
    challenge: DecimalStr
    commitments: List[DecimalStr] = Field(min_length=1, max_length=MAX_CHUNK_COUNT)
    witness: DecimalStr


class VerifyRequest(StrictModel):
    """Exactly one of ``proof_id`` (stored proof) or ``proof`` (submitted proof data)."""

    proof_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    proof: Optional[InlineProofIn] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "VerifyRequest":
        if (self.proof_id is None) == (self.proof is None):
            raise ValueError("provide exactly one of proof_id or proof")
        return self


class VerificationDetails(BaseModel):
    left_value: str
    right_value: str


class DealerVerifyResponse(BaseModel):
    verified: bool
    details: VerificationDetails


class ParticipantVerifyResponse(BaseModel):
    verified: bool
    message: str
