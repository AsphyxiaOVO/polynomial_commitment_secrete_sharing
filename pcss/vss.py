"""End-to-end workflow: threshold sharing + per-share consistency check.

This is the GUI-independent version of the legacy flow
"初始化证明者 -> 添加验证者 (x, y) -> 分发承诺值与见证 -> 验证 -> 秘密恢复":

1. ``DealerSession.create`` encodes the message, builds one degree-(k-1)
   polynomial per 31-byte chunk (``pcss.sharing``) and a :class:`Prover`
   on exactly those polynomials (``pcss.commitment``).
2. ``open_share(x, y)`` returns participant x's share (= the commitment
   values cm_i = f_i(x)) together with the witness W for challenge y.
3. A :class:`~pcss.commitment.Verifier` built from ``public_parameters()``
   checks the share.
4. ``pcss.sharing.recover_message`` recovers the message from >= k shares.

Share x-coordinates are chosen outside T (so that every share can be
verified, see ``validate_challenge``).  FRI folding is not applied (it
would break the threshold, see ``pcss.fri``).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from . import field
from .commitment import Opening, Prover, PublicParameters, validate_point_sets
from .encoding import expected_chunk_count
from .errors import ProtocolError, ValidationError
from .sharing import RandBelow, Share, SharingMetadata, split_secret

P = field.P


@dataclass
class DealerSession:
    metadata: SharingMetadata
    shares: Tuple[Share, ...]
    prover: Prover

    @classmethod
    def create(cls, message: str, threshold: int, share_count: int,
               point_sets: Sequence[Sequence[int]],
               evaluation_set: Optional[Sequence[int]] = None, *,
               x_coordinates: Optional[Sequence[int]] = None,
               coefficients: Optional[Sequence[Sequence[int]]] = None,
               require_zero_in_point_sets: bool = True,
               randbelow: Optional[RandBelow] = None) -> "DealerSession":
        """Create shares and the prover.

        ``point_sets`` holds one S_i per chunk polynomial; a single point set is
        broadcast to every chunk.  ``evaluation_set`` (T) defaults to the sorted
        union of all S_i.  ``require_zero_in_point_sets`` keeps the legacy rule
        0 ∈ S_i (note: this makes r_i(0) equal to the secret chunk).
        """
        if not isinstance(message, str):
            raise ValidationError("message must be str")
        try:
            byte_length = len(message.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValidationError(f"message is not encodable as UTF-8: {exc.reason}") from exc
        chunk_count = expected_chunk_count(byte_length)

        sets = [list(s) for s in point_sets]
        if len(sets) == 1 and chunk_count > 1:
            sets = sets * chunk_count
        if evaluation_set is None:
            evaluation_set = sorted({v for s in sets for v in s})
        sets_t, t = validate_point_sets(sets, evaluation_set, chunk_count,
                                        require_zero=require_zero_in_point_sets)

        sharing = split_secret(message, threshold, share_count, x_coordinates=x_coordinates,
                               coefficients=coefficients, excluded_x=t, randbelow=randbelow)
        prover = Prover(sharing.polynomials, sets_t, t,
                        require_zero_in_point_sets=require_zero_in_point_sets)
        return cls(metadata=sharing.metadata, shares=sharing.shares, prover=prover)

    def public_parameters(self) -> PublicParameters:
        return self.prover.public_parameters()

    def share_for(self, x: int) -> Share:
        for share in self.shares:
            if share.x == x:
                return share
        raise ValidationError(f"no share was issued for x = {x}")

    def open_share(self, x: int, y: Optional[int] = None) -> Tuple[Share, Opening]:
        """Return participant x's share and an opening (cm = share values, W) for challenge y.

        ``y`` is the verifier's challenge; if omitted a random y in [1, p-1] is drawn.
        """
        share = self.share_for(x)
        if y is None:
            y = secrets.randbelow(P - 1) + 1
        opening = self.prover.open(x, y)
        if opening.commitments != share.values:  # invariant: cm_i(x) == f_i(x) == share value
            raise ProtocolError("commitment values differ from share values")
        return share, opening
