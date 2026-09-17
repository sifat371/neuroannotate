"""Create the NeuroAnnotate v1 persistence schema.

Revision ID: 0001_v1_schema
Revises:
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0001_v1_schema"
down_revision = None
branch_labels = None
depends_on = None


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _create_cases() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_source_artifacts() -> None:
    op.create_table(
        "source_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("modality", sa.String(length=16), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("shape_x", sa.Integer(), nullable=False),
        sa.Column("shape_y", sa.Integer(), nullable=False),
        sa.Column("shape_z", sa.Integer(), nullable=False),
        sa.Column("spacing_x", sa.Float(), nullable=False),
        sa.Column("spacing_y", sa.Float(), nullable=False),
        sa.Column("spacing_z", sa.Float(), nullable=False),
        sa.Column("affine_json", sa.Text(), nullable=False),
        sa.Column("datatype", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "modality"),
    )
    op.create_index("ix_source_artifacts_case_id", "source_artifacts", ["case_id"])


def _create_inference_jobs() -> None:
    op.create_table(
        "inference_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=120), nullable=False),
        sa.Column("service_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inference_jobs_case_id", "inference_jobs", ["case_id"])
    op.create_index("ix_inference_jobs_status", "inference_jobs", ["status"])


def _create_segmentation_artifacts() -> None:
    op.create_table(
        "segmentation_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("inference_job_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("shape_x", sa.Integer(), nullable=False),
        sa.Column("shape_y", sa.Integer(), nullable=False),
        sa.Column("shape_z", sa.Integer(), nullable=False),
        sa.Column("spacing_x", sa.Float(), nullable=False),
        sa.Column("spacing_y", sa.Float(), nullable=False),
        sa.Column("spacing_z", sa.Float(), nullable=False),
        sa.Column("affine_json", sa.Text(), nullable=False),
        sa.Column("datatype", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["inference_job_id"], ["inference_jobs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inference_job_id"),
    )
    op.create_index(
        "ix_segmentation_artifacts_case_id", "segmentation_artifacts", ["case_id"]
    )


def _create_annotation_revisions() -> None:
    op.create_table(
        "annotation_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=36), nullable=True),
        sa.Column("source_segmentation_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("edit_stats_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_revision_id"], ["annotation_revisions.id"]),
        sa.ForeignKeyConstraint(
            ["source_segmentation_id"], ["segmentation_artifacts.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_annotation_revisions_case_id", "annotation_revisions", ["case_id"]
    )


def _create_exports() -> None:
    op.create_table(
        "exports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("mask_path", sa.String(length=500), nullable=False),
        sa.Column("provenance_path", sa.String(length=500), nullable=False),
        sa.Column("mask_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["annotation_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exports_case_id", "exports", ["case_id"])
    op.create_index("ix_exports_revision_id", "exports", ["revision_id"])


def _copy_legacy_rows() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    legacy_modalities = sa.Table("modalities", metadata, autoload_with=connection)
    legacy_inference = sa.Table("inference_runs", metadata, autoload_with=connection)
    legacy_revisions = sa.Table(
        "legacy_annotation_revisions", metadata, autoload_with=connection
    )
    source_artifacts = sa.Table("source_artifacts", metadata, autoload_with=connection)
    inference_jobs = sa.Table("inference_jobs", metadata, autoload_with=connection)
    segmentations = sa.Table(
        "segmentation_artifacts", metadata, autoload_with=connection
    )
    annotation_revisions = sa.Table(
        "annotation_revisions", metadata, autoload_with=connection
    )

    modality_rows = connection.execute(sa.select(legacy_modalities)).mappings().all()
    if modality_rows:
        connection.execute(
            source_artifacts.insert(),
            [
                {
                    "id": row["id"],
                    "case_id": row["case_id"],
                    "modality": row["modality"],
                    "original_filename": PurePosixPath(row["relative_path"]).name,
                    "relative_path": row["relative_path"],
                    "sha256": None,
                    "file_size": None,
                    "shape_x": row["shape_x"],
                    "shape_y": row["shape_y"],
                    "shape_z": row["shape_z"],
                    "spacing_x": row["spacing_x"],
                    "spacing_y": row["spacing_y"],
                    "spacing_z": row["spacing_z"],
                    "affine_json": row["affine_json"],
                    "datatype": None,
                    "created_at": _datetime(row["created_at"]),
                }
                for row in modality_rows
            ],
        )

    inference_rows = connection.execute(sa.select(legacy_inference)).mappings().all()
    if inference_rows:
        connection.execute(
            inference_jobs.insert(),
            [
                {
                    "id": row["id"],
                    "case_id": row["case_id"],
                    "provider": row["provider"],
                    "model_name": row["provider"],
                    "model_version": "legacy",
                    "service_version": "mvp",
                    "status": row["status"],
                    "created_at": _datetime(row["created_at"]),
                    "started_at": _datetime(row["created_at"]),
                    "completed_at": (
                        _datetime(row["created_at"])
                        if row["status"] == "completed"
                        else None
                    ),
                    "error_message": None,
                    "failure_category": None,
                    "provenance_json": row["metadata_json"] or "{}",
                }
                for row in inference_rows
            ],
        )

    geometry_by_case: dict[str, Any] = {}
    for row in modality_rows:
        geometry_by_case.setdefault(row["case_id"], row)
    completed_rows = [row for row in inference_rows if row["status"] == "completed"]
    if completed_rows:
        connection.execute(
            segmentations.insert(),
            [
                {
                    "id": row["id"],
                    "case_id": row["case_id"],
                    "inference_job_id": row["id"],
                    "relative_path": row["relative_path"],
                    "sha256": None,
                    "shape_x": geometry_by_case[row["case_id"]]["shape_x"],
                    "shape_y": geometry_by_case[row["case_id"]]["shape_y"],
                    "shape_z": geometry_by_case[row["case_id"]]["shape_z"],
                    "spacing_x": geometry_by_case[row["case_id"]]["spacing_x"],
                    "spacing_y": geometry_by_case[row["case_id"]]["spacing_y"],
                    "spacing_z": geometry_by_case[row["case_id"]]["spacing_z"],
                    "affine_json": geometry_by_case[row["case_id"]]["affine_json"],
                    "datatype": "unknown",
                    "created_at": _datetime(row["created_at"]),
                }
                for row in completed_rows
            ],
        )

    revision_rows = connection.execute(sa.select(legacy_revisions)).mappings().all()
    if revision_rows:
        connection.execute(
            annotation_revisions.insert(),
            [
                {
                    "id": row["id"],
                    "case_id": row["case_id"],
                    "parent_revision_id": None,
                    "source_segmentation_id": row["source_inference_id"],
                    "relative_path": row["relative_path"],
                    "sha256": None,
                    "note": row["note"],
                    "edit_stats_json": "{}",
                    "created_at": _datetime(row["created_at"]),
                }
                for row in revision_rows
            ],
        )


def upgrade() -> None:
    connection = op.get_bind()
    table_names = set(sa.inspect(connection).get_table_names())
    is_legacy = {"cases", "modalities", "inference_runs", "annotation_revisions"} <= table_names

    if not is_legacy:
        _create_cases()
        _create_source_artifacts()
        _create_inference_jobs()
        _create_segmentation_artifacts()
        _create_annotation_revisions()
        _create_exports()
        return

    op.add_column(
        "cases", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    connection.execute(sa.text("UPDATE cases SET updated_at = created_at"))
    with op.batch_alter_table("cases") as batch_op:
        batch_op.alter_column("updated_at", nullable=False)

    op.rename_table("annotation_revisions", "legacy_annotation_revisions")
    _create_source_artifacts()
    _create_inference_jobs()
    _create_segmentation_artifacts()
    _create_annotation_revisions()
    _create_exports()
    _copy_legacy_rows()

    op.drop_table("legacy_annotation_revisions")
    op.drop_table("inference_runs")
    op.drop_table("modalities")


def downgrade() -> None:
    op.drop_index("ix_exports_revision_id", table_name="exports")
    op.drop_index("ix_exports_case_id", table_name="exports")
    op.drop_table("exports")
    op.drop_index("ix_annotation_revisions_case_id", table_name="annotation_revisions")
    op.drop_table("annotation_revisions")
    op.drop_index("ix_segmentation_artifacts_case_id", table_name="segmentation_artifacts")
    op.drop_table("segmentation_artifacts")
    op.drop_index("ix_inference_jobs_status", table_name="inference_jobs")
    op.drop_index("ix_inference_jobs_case_id", table_name="inference_jobs")
    op.drop_table("inference_jobs")
    op.drop_index("ix_source_artifacts_case_id", table_name="source_artifacts")
    op.drop_table("source_artifacts")
    op.drop_table("cases")
