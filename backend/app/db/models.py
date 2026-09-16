from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    modalities: Mapped[list[ModalityArtifact]] = relationship(cascade="all, delete-orphan")
    inference_runs: Mapped[list[InferenceRun]] = relationship(cascade="all, delete-orphan")
    revisions: Mapped[list[AnnotationRevision]] = relationship(cascade="all, delete-orphan")


class ModalityArtifact(Base):
    __tablename__ = "modalities"
    __table_args__ = (UniqueConstraint("case_id", "modality"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    modality: Mapped[str] = mapped_column(String(16))
    relative_path: Mapped[str] = mapped_column(String(500))
    shape_x: Mapped[int]
    shape_y: Mapped[int]
    shape_z: Mapped[int]
    spacing_x: Mapped[float]
    spacing_y: Mapped[float]
    spacing_z: Mapped[float]
    affine_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InferenceRun(Base):
    __tablename__ = "inference_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    relative_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="completed")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnnotationRevision(Base):
    __tablename__ = "annotation_revisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_inference_id: Mapped[str] = mapped_column(String(64))
    relative_path: Mapped[str] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
