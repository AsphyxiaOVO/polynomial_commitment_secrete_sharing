"""Shared schema types.

Field elements are up to 255 bits, beyond JavaScript's safe-integer range, so
they travel as **decimal strings**.  Range checks (< p) happen in the core and
are reported as 422 like every other validation error.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated

#: Non-negative decimal integer as a string (p < 10^78).
DecimalStr = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,78}$")]


class StrictModel(BaseModel):
    """Requests reject unknown fields (e.g. a client-supplied ``role``)."""

    model_config = ConfigDict(extra="forbid")


class PublicParametersOut(BaseModel):
    point_sets: List[List[str]]
    evaluation_set: List[str]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


def to_str_list(values) -> List[str]:
    return [str(v) for v in values]
