"""SQLAlchemy models and data-ownership boundaries.

Field elements (up to 255 bits) do not fit SQLite INTEGER, so they are
stored as decimal strings (lists as JSON arrays of decimal strings).

Ownership
---------
users                    identity + role (role is only changed by the admin CLI)
sharing_tasks            owned by exactly one dealer (``dealer_id``); public metadata only
shares                   one row per (task, recipient); readable only by that recipient
proofs                   issued by the task dealer for one recipient's share coordinate
task_secrets             SENSITIVE: the secret sharing polynomials (constant terms = message chunks);
                         used only to generate proofs; never returned by any endpoint
task_verification_keys   SENSITIVE: r_i (interpolants of f_i on S_i). Needed by the verifier but
                         they leak information about f_i (see README), so they stay server-side.

The demo stores everything unencrypted in a local SQLite file: NOT suitable
for real secrets.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('dealer', 'participant')", name="ck_user_role"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SharingTask(Base):
    __tablename__ = "sharing_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('created', 'distributed')", name="ck_task_status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    dealer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="created")
    threshold: Mapped[int] = mapped_column(Integer)
    total_shares: Mapped[int] = mapped_column(Integer)
    original_length: Mapped[int] = mapped_column(Integer)
    chunk_size: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    point_sets: Mapped[str] = mapped_column(Text)        # JSON [[str]] - public
    evaluation_set: Mapped[str] = mapped_column(Text)    # JSON [str]   - public
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    distributed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    shares: Mapped[List["ShareRecord"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="ShareRecord.position")


class ShareRecord(Base):
    __tablename__ = "shares"
    __table_args__ = (UniqueConstraint("task_id", "participant_id", name="uq_share_recipient"),
                      UniqueConstraint("task_id", "x", name="uq_share_x"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("sharing_tasks.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)       # order in the dealer's participant list
    x: Mapped[str] = mapped_column(String(80))           # decimal string (public coordinate)
    share_values: Mapped[str] = mapped_column(Text)      # JSON [str] - private to the recipient

    task: Mapped[SharingTask] = relationship(back_populates="shares")


class ProofRecord(Base):
    __tablename__ = "proofs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("sharing_tasks.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    x: Mapped[str] = mapped_column(String(80))
    challenge: Mapped[str] = mapped_column(String(80))
    commitments: Mapped[str] = mapped_column(Text)       # JSON [str] (= the recipient's share values)
    witness: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskSecret(Base):
    """SENSITIVE internal state: secret polynomials. Never serialised to clients or logs."""

    __tablename__ = "task_secrets"

    task_id: Mapped[str] = mapped_column(ForeignKey("sharing_tasks.id", ondelete="CASCADE"),
                                         primary_key=True)
    polynomials: Mapped[str] = mapped_column(Text)       # JSON [[str]] low-to-high coefficients

    def __repr__(self) -> str:
        return f"TaskSecret(task_id={self.task_id!r}, polynomials=<redacted>)"


class TaskVerificationKey(Base):
    """SENSITIVE server-side verification parameters r_i (they reveal f_i on S_i)."""

    __tablename__ = "task_verification_keys"

    task_id: Mapped[str] = mapped_column(ForeignKey("sharing_tasks.id", ondelete="CASCADE"),
                                         primary_key=True)
    r_polynomials: Mapped[str] = mapped_column(Text)     # JSON [[str]]

    def __repr__(self) -> str:
        return f"TaskVerificationKey(task_id={self.task_id!r}, r_polynomials=<redacted>)"
