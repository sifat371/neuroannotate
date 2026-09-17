from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_uuid() -> str:
    """Return a UUID suitable for persisted entity identifiers."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    source_artifacts: Mapped[list[SourceArtifact]] = relationship(
        cascade="all, delete-orphan"
    )
    inference_jobs: Mapped[list[InferenceJob]] = relationship(cascade="all, delete-orphan")
    segmentation_artifacts: Mapped[list[SegmentationArtifact]] = relationship(
        cascade="all, delete-orphan"
    )
    revisions: Mapped[list[AnnotationRevision]] = relationship(cascade="all, delete-orphan")
    exports: Mapped[list[ExportArtifact]] = relationship(cascade="all, delete-orphan")


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    __table_args__ = (UniqueConstraint("case_id", "modality"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    modality: Mapped[str] = mapped_column(String(16))
    original_filename: Mapped[str] = mapped_column(String(255))
    relative_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    shape_x: Mapped[int]
    shape_y: Mapped[int]
    shape_z: Mapped[int]
    spacing_x: Mapped[float]
    spacing_y: Mapped[float]
    spacing_z: Mapped[float]
    affine_json: Mapped[str] = mapped_column(Text)
    datatype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InferenceJob(Base):
    __tablename__ = "inference_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(120))
    model_version: Mapped[str] = mapped_column(String(120))
    service_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")

    segmentation: Mapped[SegmentationArtifact | None] = relationship(
        back_populates="inference_job", uselist=False
    )


class SegmentationArtifact(Base):
    __tablename__ = "segmentation_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    inference_job_id: Mapped[str] = mapped_column(
        ForeignKey("inference_jobs.id", ondelete="CASCADE"), unique=True
    )
    relative_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shape_x: Mapped[int]
    shape_y: Mapped[int]
    shape_z: Mapped[int]
    spacing_x: Mapped[float]
    spacing_y: Mapped[float]
    spacing_z: Mapped[float]
    affine_json: Mapped[str] = mapped_column(Text)
    datatype: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    inference_job: Mapped[InferenceJob] = relationship(back_populates="segmentation")


class AnnotationRevision(Base):
    __tablename__ = "annotation_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    parent_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("annotation_revisions.id"), nullable=True
    )
    source_segmentation_id: Mapped[str] = mapped_column(
        ForeignKey("segmentation_artifacts.id")
    )
    relative_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    edit_stats_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExportArtifact(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("annotation_revisions.id"), index=True
    )
    mask_path: Mapped[str] = mapped_column(String(500))
    provenance_path: Mapped[str] = mapped_column(String(500))
    mask_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
