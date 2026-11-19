"""Proof generation (dealer) and proof verification (dealer / recipients).

Two different things — do not confuse them:

* **Evaluation-consistency proof** (what this service provides): for a share
  coordinate x and challenge y, the dealer returns cm_i = f_i(x) and the
  witness W; verification checks
  ``W * Z_T(x) == sum_i (cm_i - r_i(x)) * y^i * Z_{T\\S_i}(x)`` with the
  server-side r_i.  It shows that (cm, W) are consistent with r_i.
* **Share validity** (NOT provided): a guarantee that a participant's share lies
  on the dealer's single degree-(k-1) polynomial.  The retained scheme is not
  binding: a party knowing r_i can build a passing (cm', W') for any cm'.

Verification never loads the secret polynomials: it only uses S_i, T and r_i
through :class:`pcss.commitment.Verifier`, the same function for every role.
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from pcss.commitment import Prover, PublicParameters, Verifier, validate_challenge
from pcss.config import FIELD_MODULUS
from pcss.errors import ProtocolError

from app.errors import ConflictError, InvalidRequestError, NotFoundError
from app.security.authorization import Action, Actor, ensure_allowed
from app.storage.models import ProofRecord, SharingTask
from app.storage.repository import Repository, ints_to_json, json_to_ints

from .common import load_task

logger = logging.getLogger("app.verification")


@dataclass(frozen=True)
class ProofView:
    proof_id: str
    sharing_id: str
    participant_id: str
    x: int
    challenge: int
    commitments: List[int]
    witness: int
    point_sets: List[List[int]]
    evaluation_set: List[int]
    created_at: datetime


@dataclass(frozen=True)
class InlineProof:
    x: int
    challenge: int
    commitments: List[int]
    witness: int


@dataclass(frozen=True)
class VerificationOutcome:
    verified: bool
    left_value: int
    right_value: int
    caller_is_task_dealer: bool   # decides how much detail the API returns


def _point_sets(task: SharingTask) -> List[List[int]]:
    return [[int(v) for v in row] for row in json.loads(task.point_sets)]


def _evaluation_set(task: SharingTask) -> List[int]:
    return [int(v) for v in json.loads(task.evaluation_set)]


class VerificationService:
    def __init__(self, repo: Repository):
        self.repo = repo

    # -------------------------------------------------------------- generate --
    def generate_proof(self, actor: Actor, task_id: str, participant_id: str,
                       challenge: Optional[int] = None) -> ProofView:
        """Proof for the share of ``participant_id`` (x = that recipient's coordinate).

        Proofs are only produced at issued share coordinates: an opening at a
        fresh x would hand out a new evaluation f_i(x), i.e. an extra share.
        If ``challenge`` is omitted it is drawn uniformly from [1, p-1] with ``secrets``.
        """
        task, relation = load_task(self.repo, actor, task_id)
        ensure_allowed(Action.GENERATE_PROOF, actor, relation)
        if task.status != "distributed":
            raise ConflictError("Shares must be distributed before proofs are generated")
        share = self.repo.get_share(task_id, participant_id)
        if share is None:
            raise InvalidRequestError("participant_id is not a share recipient of this task")
        y = challenge if challenge is not None else secrets.randbelow(FIELD_MODULUS - 1) + 1
        x = int(share.x)
        point_sets, t = _point_sets(task), _evaluation_set(task)
        validate_challenge(x, y, t)                               # x ∉ T, 1 <= y < p

        prover = Prover(self.repo.get_task_polynomials(task_id), point_sets, t)
        opening = prover.open(x, y)
        if list(opening.commitments) != json_to_ints(share.share_values):
            raise ProtocolError("stored share does not match the dealer polynomials")

        record = ProofRecord(id=uuid.uuid4().hex, task_id=task_id, participant_id=participant_id,
                             x=str(x), challenge=str(y), commitments=ints_to_json(opening.commitments),
                             witness=str(opening.witness))
        self.repo.add_proof(record)
        self.repo.commit()
        logger.info("proof generated task=%s proof=%s", task_id, record.id)
        return ProofView(proof_id=record.id, sharing_id=task_id, participant_id=participant_id, x=x,
                         challenge=y, commitments=list(opening.commitments),
                         witness=opening.witness, point_sets=point_sets, evaluation_set=t,
                         created_at=record.created_at)

    # ---------------------------------------------------------------- verify --
    def verify(self, actor: Actor, task_id: str, *, proof_id: Optional[str] = None,
               proof: Optional[InlineProof] = None) -> VerificationOutcome:
        """Verify either a stored proof (``proof_id``) or a submitted one (``proof``).

        * ``proof_id``: recipients may only use proofs issued for their own share
          (others get 404); the task dealer may use any proof of the task.  In this
          mode the witness never has to leave the server.
        * inline ``proof``: any task member may submit proof data they hold.
        Mathematical failure is a normal result (``verified=False``), not an error.
        """
        task, relation = load_task(self.repo, actor, task_id)
        ensure_allowed(Action.VERIFY_PROOF, actor, relation)
        if (proof_id is None) == (proof is None):
            raise InvalidRequestError("Provide exactly one of proof_id or proof")
        if proof_id is not None:
            record = self.repo.get_proof(task_id, proof_id)
            if record is None or (not relation.is_owner and record.participant_id != actor.user_id):
                raise NotFoundError("Proof not found")
            proof = InlineProof(x=int(record.x), challenge=int(record.challenge),
                                commitments=json_to_ints(record.commitments),
                                witness=int(record.witness))
        if proof is None:  # unreachable, keeps type checkers and -O runs honest
            raise InvalidRequestError("Provide exactly one of proof_id or proof")

        params = PublicParameters(
            point_sets=tuple(tuple(s) for s in _point_sets(task)),
            evaluation_set=tuple(_evaluation_set(task)),
            r_polynomials=tuple(tuple(r) for r in self.repo.get_r_polynomials(task_id)))
        result = Verifier(params).verify(proof.x, proof.challenge, proof.commitments, proof.witness)
        logger.info("proof verified task=%s verified=%s", task_id, result.valid)
        return VerificationOutcome(verified=result.valid, left_value=result.left,
                                   right_value=result.right, caller_is_task_dealer=relation.is_owner)
