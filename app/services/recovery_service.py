"""Secret recovery from shares submitted by the caller.

The service never reads stored shares to "fill up" the threshold: the caller
must obtain >= k shares through legitimate out-of-band cooperation and submit
them.  Format checks (count, distinct x, field range, issued coordinates) are
NOT a cryptographic validity check - a modified share that is well-formed is
only detected if redundant shares (> k) are inconsistent or decoding fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from pcss.sharing import Share, recover_message

from app.errors import InvalidRequestError
from app.security.authorization import Action, Actor, ensure_allowed
from app.storage.repository import Repository

from .common import load_task, metadata_of

logger = logging.getLogger("app.recovery")


@dataclass(frozen=True)
class RecoveryOutcome:
    sharing_id: str
    message: str
    shares_used: int
    threshold: int


class RecoveryService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def recover(self, actor: Actor, task_id: str,
                submitted: Sequence[Tuple[int, Sequence[int]]]) -> RecoveryOutcome:
        task, relation = load_task(self.repo, actor, task_id)
        ensure_allowed(Action.RECOVER_SECRET, actor, relation)
        issued = set(self.repo.list_share_coordinates(task_id))   # public coordinates only
        not_issued = [x for x, _ in submitted if x not in issued]
        if not_issued:
            raise InvalidRequestError(f"x-coordinates not issued for this task: {not_issued}")
        shares: List[Share] = [Share(x=x, values=tuple(values)) for x, values in submitted]
        message = recover_message(shares, metadata_of(task))      # validates count / x / range
        logger.info("secret recovered task=%s shares=%d", task_id, len(shares))
        return RecoveryOutcome(sharing_id=task_id, message=message, shares_used=len(shares),
                               threshold=task.threshold)
