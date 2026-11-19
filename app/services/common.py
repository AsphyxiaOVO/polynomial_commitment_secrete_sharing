"""Helpers and read models shared by the services."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from pcss.sharing import SharingMetadata

from app.errors import NotFoundError
from app.security.authorization import Actor, TaskRelation
from app.storage.models import SharingTask
from app.storage.repository import Repository


@dataclass(frozen=True)
class ParticipantView:
    participant_id: str
    x: int


@dataclass(frozen=True)
class TaskView:
    """Public, non-sensitive description of a sharing task."""

    sharing_id: str
    dealer_id: str
    status: str
    threshold: int
    total_shares: int
    chunk_count: int
    chunk_size: int
    original_length: int
    participants: List[ParticipantView]
    point_sets: List[List[int]]
    evaluation_set: List[int]
    created_at: datetime
    distributed_at: Optional[datetime]


def metadata_of(task: SharingTask) -> SharingMetadata:
    return SharingMetadata(threshold=task.threshold, share_count=task.total_shares,
                           original_length=task.original_length, chunk_count=task.chunk_count,
                           chunk_size=task.chunk_size)


def task_view(task: SharingTask) -> TaskView:
    return TaskView(
        sharing_id=task.id, dealer_id=task.dealer_id, status=task.status,
        threshold=task.threshold, total_shares=task.total_shares, chunk_count=task.chunk_count,
        chunk_size=task.chunk_size, original_length=task.original_length,
        participants=[ParticipantView(s.participant_id, int(s.x)) for s in task.shares],
        point_sets=[[int(v) for v in row] for row in json.loads(task.point_sets)],
        evaluation_set=[int(v) for v in json.loads(task.evaluation_set)],
        created_at=task.created_at, distributed_at=task.distributed_at)


def load_task(repo: Repository, actor: Actor, task_id: str) -> Tuple[SharingTask, TaskRelation]:
    """Load a task and the caller's relation to it (authorization is decided by the caller)."""
    task = repo.get_task(task_id)
    if task is None:
        raise NotFoundError("Sharing task not found")
    relation = TaskRelation(is_owner=task.dealer_id == actor.user_id,
                            is_recipient=repo.is_recipient(task_id, actor.user_id))
    return task, relation
