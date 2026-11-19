from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, StrictInt

from pcss.config import MAX_CHUNK_COUNT, MAX_SHARE_COUNT

from .common import DecimalStr, StrictModel


class ShareIn(StrictModel):
    x: StrictInt
    values: List[DecimalStr] = Field(min_length=1, max_length=MAX_CHUNK_COUNT)


class RecoverRequest(StrictModel):
    shares: List[ShareIn] = Field(min_length=1, max_length=MAX_SHARE_COUNT)


class RecoverResponse(BaseModel):
    sharing_id: str
    message: str
    shares_used: int
    threshold: int
    note: str = ("Recovery succeeded with well-formed shares; this is not a cryptographic proof "
                 "that every submitted share is authentic.")
