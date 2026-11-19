"""Create sharing tasks, distribute shares, and let recipients read their own share."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import List, Sequence

from pcss.commitment import Prover
from pcss.config import FIELD_MODULUS
from pcss.sharing import split_secret, validate_sharing_parameters

from app.errors import ConflictError, InvalidRequestError, NotFoundError
from app.security.authorization import Action, Actor, ensure_allowed
from app.storage.models import ShareRecord, SharingTask, TaskSecret, TaskVerificationKey
from app.storage.repository import Repository, ints_to_json, json_to_ints, nested_ints_to_json

from .common import TaskView, load_task, task_view

logger = logging.getLogger("app.sharing")

#: Point set used by the API for every chunk: S_i = T = {p - 1}.
#: * 0 is NOT used: with the legacy rule 0 ∈ S_i, r_i(0) equals the secret chunk.
#: * a single point keeps the information revealed by r_i / witnesses to one
#:   evaluation f_i(p - 1) per chunk (see README "Security limitations").
#: * p - 1 can never collide with a share coordinate (shares use x = 1..n).
API_EVALUATION_POINT = FIELD_MODULUS - 1


@dataclass(frozen=True)
class OwnShareView:
    task: TaskView
    participant_id: str
    x: int
    values: List[int]


class SharingService:
    def __init__(self, repo: Repository):
        self.repo = repo

    # ----------------------------------------------------------------- create --
    def create(self, actor: Actor, message: str, threshold: int,
               participant_ids: Sequence[str]) -> TaskView:
        ensure_allowed(Action.CREATE_SHARING, actor)
        participant_ids = list(participant_ids)
        if len(set(participant_ids)) != len(participant_ids):
            raise InvalidRequestError("participant_ids contains duplicates")
        validate_sharing_parameters(threshold, len(participant_ids))   # 2 <= k <= n < p, limits
        found = {u.id: u for u in self.repo.get_users(participant_ids)}
        unknown = [pid for pid in participant_ids if pid not in found or not found[pid].is_active]
        if unknown:
            raise InvalidRequestError(f"Unknown or inactive participants: {unknown}")

        t = API_EVALUATION_POINT
        sharing = split_secret(message, threshold, len(participant_ids), excluded_x=[t])
        meta = sharing.metadata
        point_sets = [[t] for _ in range(meta.chunk_count)]
        prover = Prover(sharing.polynomials, point_sets, [t])          # computes r_i
        r_polys = prover.public_parameters().r_polynomials

        task_id = uuid.uuid4().hex
        task = SharingTask(
            id=task_id, dealer_id=actor.user_id, status="created", threshold=meta.threshold,
            total_shares=meta.share_count, original_length=meta.original_length,
            chunk_size=meta.chunk_size, chunk_count=meta.chunk_count,
            point_sets=nested_ints_to_json(point_sets), evaluation_set=ints_to_json([t]))
        shares = [ShareRecord(task_id=task_id, participant_id=pid, position=i, x=str(share.x),
                              share_values=ints_to_json(share.values))
                  for i, (pid, share) in enumerate(zip(participant_ids, sharing.shares))]
        self.repo.add_task(task,
                           TaskSecret(task_id=task_id, polynomials=nested_ints_to_json(sharing.polynomials)),
                           TaskVerificationKey(task_id=task_id, r_polynomials=nested_ints_to_json(r_polys)),
                           shares)
        self.repo.commit()
        # Log identifiers and sizes only - never the message, shares or coefficients.
        logger.info("sharing task created id=%s dealer=%s k=%d n=%d chunks=%d",
                    task_id, actor.user_id, meta.threshold, meta.share_count, meta.chunk_count)
        return self.get(actor, task_id)

    # ------------------------------------------------------------------- read --
    def get(self, actor: Actor, task_id: str) -> TaskView:
        task, relation = load_task(self.repo, actor, task_id)
        ensure_allowed(Action.VIEW_TASK, actor, relation)
        return task_view(task)

    # ------------------------------------------------------------- distribute --
    def distribute(self, actor: Actor, task_id: str) -> TaskView:
        """Grant every recipient access to their share.

        Idempotency rule: the first call moves the task from ``created`` to
        ``distributed``; any later call raises ConflictError (HTTP 409) and changes
        nothing.  Shares are generated once at creation and never regenerated.
        """
        task, relation = load_task(self.repo, actor, task_id)
        ensure_allowed(Action.DISTRIBUTE_SHARES, actor, relation)
        if not self.repo.mark_distributed(task_id):
            self.repo.rollback()
            raise ConflictError("Shares of this task have already been distributed")
        self.repo.commit()
        logger.info("sharing task distributed id=%s", task_id)
        self.repo.session.refresh(task)
        return task_view(task)

    # -------------------------------------------------------------- own share --
    def get_own_share(self, actor: Actor, task_id: str) -> OwnShareView:
        """Return ONLY the caller's share; the lookup key is the authenticated user id."""
        task, relation = load_task(self.repo, actor, task_id)
        ensure_allowed(Action.VIEW_OWN_SHARE, actor, relation)
        if task.status != "distributed":
            raise ConflictError("Shares of this task have not been distributed yet")
        record = self.repo.get_share(task_id, actor.user_id)
        if record is None:  # cannot happen: relation.is_recipient was checked above
            raise NotFoundError("Share not found")
        return OwnShareView(task=task_view(task), participant_id=actor.user_id, x=int(record.x),
                            values=json_to_ints(record.share_values))
