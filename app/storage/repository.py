"""Data access. Services talk to this class, never to SQLAlchemy sessions directly."""

from __future__ import annotations

import json
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import (ProofRecord, ShareRecord, SharingTask, TaskSecret, TaskVerificationKey, User,
                     utcnow)


def ints_to_json(values: Iterable[int]) -> str:
    return json.dumps([str(v) for v in values])


def json_to_ints(text: str) -> List[int]:
    return [int(v) for v in json.loads(text)]


def nested_ints_to_json(rows: Iterable[Iterable[int]]) -> str:
    return json.dumps([[str(v) for v in row] for row in rows])


def json_to_nested_ints(text: str) -> List[List[int]]:
    return [[int(v) for v in row] for row in json.loads(text)]


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # ----------------------------------------------------------- transactions --
    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    # ------------------------------------------------------------------ users --
    def get_user(self, user_id: str) -> Optional[User]:
        return self.session.get(User, user_id)

    def get_users(self, user_ids: Sequence[str]) -> List[User]:
        if not user_ids:
            return []
        return list(self.session.scalars(select(User).where(User.id.in_(list(user_ids)))))

    def add_user(self, user: User) -> User:
        self.session.add(user)
        return user

    # ------------------------------------------------------------------ tasks --
    def add_task(self, task: SharingTask, secret: TaskSecret, key: TaskVerificationKey,
                 shares: Sequence[ShareRecord]) -> None:
        self.session.add(task)
        self.session.add(secret)
        self.session.add(key)
        self.session.add_all(list(shares))

    def get_task(self, task_id: str) -> Optional[SharingTask]:
        return self.session.get(SharingTask, task_id)

    def mark_distributed(self, task_id: str) -> bool:
        """Atomic created -> distributed transition. Returns False if it was already distributed."""
        result = self.session.execute(
            update(SharingTask)
            .where(SharingTask.id == task_id, SharingTask.status == "created")
            .values(status="distributed", distributed_at=utcnow()))
        return result.rowcount == 1

    # ----------------------------------------------------------------- shares --
    def get_share(self, task_id: str, participant_id: str) -> Optional[ShareRecord]:
        return self.session.scalars(select(ShareRecord).where(
            ShareRecord.task_id == task_id, ShareRecord.participant_id == participant_id)).first()

    def is_recipient(self, task_id: str, user_id: str) -> bool:
        return self.get_share(task_id, user_id) is not None

    def list_share_coordinates(self, task_id: str) -> List[int]:
        """Public x-coordinates issued for a task (share VALUES are not loaded)."""
        return [int(x) for x in self.session.scalars(
            select(ShareRecord.x).where(ShareRecord.task_id == task_id))]

    # ------------------------------------------------------- sensitive state --
    def get_task_polynomials(self, task_id: str) -> List[List[int]]:
        secret = self.session.get(TaskSecret, task_id)
        if secret is None:
            raise LookupError(f"missing secret state for task {task_id}")
        return json_to_nested_ints(secret.polynomials)

    def get_r_polynomials(self, task_id: str) -> List[List[int]]:
        key = self.session.get(TaskVerificationKey, task_id)
        if key is None:
            raise LookupError(f"missing verification parameters for task {task_id}")
        return json_to_nested_ints(key.r_polynomials)

    # ----------------------------------------------------------------- proofs --
    def add_proof(self, proof: ProofRecord) -> None:
        self.session.add(proof)

    def get_proof(self, task_id: str, proof_id: str) -> Optional[ProofRecord]:
        proof = self.session.get(ProofRecord, proof_id)
        return proof if proof is not None and proof.task_id == task_id else None
