from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, StrictInt, StringConstraints
from typing_extensions import Annotated

from pcss.config import MAX_MESSAGE_BYTES, MAX_SHARE_COUNT

from .common import PublicParametersOut, StrictModel, to_str_list

UserId = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class CreateSharingRequest(StrictModel):
    """Only message, threshold and recipients: the system generates the polynomials."""

    message: str = Field(max_length=MAX_MESSAGE_BYTES,
                         description=f"UTF-8 secret; at most {MAX_MESSAGE_BYTES} bytes")
    threshold: StrictInt = Field(description="Recovery threshold k (polynomial degree = k - 1)")
    participant_ids: List[UserId] = Field(min_length=2, max_length=MAX_SHARE_COUNT,
                                          description="Share recipients; n = len(participant_ids)")


class ParticipantOut(BaseModel):
    participant_id: str
    x: int


class SharingTaskOut(BaseModel):
    sharing_id: str
    dealer_id: str
    status: str
    threshold: int
    total_shares: int
    chunk_count: int
    chunk_size: int
    original_length: int
    participants: List[ParticipantOut]
    public_parameters: PublicParametersOut
    created_at: datetime
    distributed_at: Optional[datetime] = None

    @classmethod
    def from_view(cls, v) -> "SharingTaskOut":
        return cls(
            sharing_id=v.sharing_id, dealer_id=v.dealer_id, status=v.status, threshold=v.threshold,
            total_shares=v.total_shares, chunk_count=v.chunk_count, chunk_size=v.chunk_size,
            original_length=v.original_length,
            participants=[ParticipantOut(participant_id=p.participant_id, x=p.x) for p in v.participants],
            public_parameters=PublicParametersOut(
                point_sets=[to_str_list(s) for s in v.point_sets],
                evaluation_set=to_str_list(v.evaluation_set)),
            created_at=v.created_at, distributed_at=v.distributed_at)


class OwnShareOut(BaseModel):
    sharing_id: str
    participant_id: str
    x: int
    values: List[str] = Field(description="f_j(x) for every chunk j, decimal strings")
    threshold: int
    total_shares: int
    chunk_count: int
    chunk_size: int
    original_length: int

    @classmethod
    def from_view(cls, v) -> "OwnShareOut":
        t = v.task
        return cls(sharing_id=t.sharing_id, participant_id=v.participant_id, x=v.x,
                   values=to_str_list(v.values), threshold=t.threshold,
                   total_shares=t.total_shares, chunk_count=t.chunk_count,
                   chunk_size=t.chunk_size, original_length=t.original_length)
