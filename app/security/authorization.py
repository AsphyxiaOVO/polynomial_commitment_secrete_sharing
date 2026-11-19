"""Role-based + resource-based access control, kept separate from all algorithms.

A decision depends on three things:

1. the caller's **system role** (read from the database, never from the request);
2. the caller's **relation to the sharing task** (owner dealer / share recipient);
3. the targeted **resource** (e.g. "my own share" vs. somebody else's).

Permission matrix (``POLICY``)

=====================  ==========================  ==========================
Action                 Dealer                      Participant
=====================  ==========================  ==========================
create sharing         allow                       deny
view task metadata     owner or recipient          recipient
distribute shares      owner only                  deny
view own share         only if recipient           only if recipient
view others' shares    deny (no such endpoint)     deny (no such endpoint)
generate proof         owner only                  deny
verify proof           owner or recipient          recipient
recover secret         owner or recipient          recipient
=====================  ==========================  ==========================

Callers that are not members of a task get 404 (the task's existence is
hidden); members lacking a permission get 403.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional

from app.errors import NotFoundError, PermissionDeniedError


class Role(str, Enum):
    DEALER = "dealer"
    PARTICIPANT = "participant"


class Action(str, Enum):
    CREATE_SHARING = "create_sharing"
    VIEW_TASK = "view_task"
    DISTRIBUTE_SHARES = "distribute_shares"
    VIEW_OWN_SHARE = "view_own_share"
    GENERATE_PROOF = "generate_proof"
    VERIFY_PROOF = "verify_proof"
    RECOVER_SECRET = "recover_secret"


@dataclass(frozen=True)
class Actor:
    """Authenticated caller; built from the database record, not from client input."""

    user_id: str
    role: Role


@dataclass(frozen=True)
class TaskRelation:
    is_owner: bool        # the caller created the task (always a dealer)
    is_recipient: bool    # the caller was assigned a share in the task

    @property
    def is_member(self) -> bool:
        return self.is_owner or self.is_recipient


Rule = Callable[[Actor, Optional[TaskRelation]], bool]


def _dealer_owner(actor: Actor, rel: Optional[TaskRelation]) -> bool:
    return actor.role is Role.DEALER and rel is not None and rel.is_owner


def _member(actor: Actor, rel: Optional[TaskRelation]) -> bool:
    return rel is not None and rel.is_member


def _recipient(actor: Actor, rel: Optional[TaskRelation]) -> bool:
    return rel is not None and rel.is_recipient


POLICY: Dict[Action, Rule] = {
    Action.CREATE_SHARING: lambda actor, rel: actor.role is Role.DEALER,
    Action.VIEW_TASK: _member,
    Action.DISTRIBUTE_SHARES: _dealer_owner,
    Action.VIEW_OWN_SHARE: _recipient,
    Action.GENERATE_PROOF: _dealer_owner,
    Action.VERIFY_PROOF: _member,
    Action.RECOVER_SECRET: _member,
}

_DENIAL_MESSAGES = {
    Action.CREATE_SHARING: "Only dealers can create secret sharing tasks",
    Action.DISTRIBUTE_SHARES: "Only the dealer who created this task can distribute its shares",
    Action.VIEW_OWN_SHARE: "You are not a share recipient of this task",
    Action.GENERATE_PROOF: "Only the dealer who created this task can generate proofs",
}


def is_allowed(action: Action, actor: Actor, relation: Optional[TaskRelation] = None) -> bool:
    return POLICY[action](actor, relation)


def ensure_allowed(action: Action, actor: Actor, relation: Optional[TaskRelation] = None) -> None:
    """Raise NotFoundError for non-members of a task, PermissionDeniedError otherwise."""
    if is_allowed(action, actor, relation):
        return
    if relation is not None and not relation.is_member:
        raise NotFoundError("Sharing task not found")
    raise PermissionDeniedError(_DENIAL_MESSAGES.get(action, "Operation not permitted"))
