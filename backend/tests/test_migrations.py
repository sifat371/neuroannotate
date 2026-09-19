import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.db.session import configure_database, run_migrations
from app.main import create_app


@pytest.fixture
def seed_mvp_db() -> Callable[[Path], Path]:
    fixture_path = Path(__file__).parent / "fixtures" / "mvp_schema.sql"

    def seed(database_path: Path) -> Path:
        with sqlite3.connect(database_path) as connection:
            connection.executescript(fixture_path.read_text(encoding="utf-8"))
        return database_path

    return seed


def test_mvp_database_migrates_without_losing_case(
    tmp_path: Path,
    seed_mvp_db: Callable[[Path], Path],
) -> None:
    database_path = seed_mvp_db(tmp_path / "mvp.db")
    database_url = f"sqlite:///{database_path}"

    run_migrations(database_url)

    engine = create_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {
            "cases",
            "source_artifacts",
            "inference_jobs",
            "segmentation_artifacts",
            "annotation_revisions",
            "exports",
            "alembic_version",
        } <= tables
        with engine.connect() as connection:
            assert connection.execute(text("select count(*) from cases")).scalar_one() == 1
            assert (
                connection.execute(text("select count(*) from source_artifacts")).scalar_one()
                == 3
            )
            assert (
                connection.execute(text("select count(*) from annotation_revisions")).scalar_one()
                == 1
            )
            migrated_source = connection.execute(
                text(
                    "select id, original_filename, relative_path, sha256, file_size "
                    "from source_artifacts where modality = 'DWI'"
                )
            ).one()
            assert migrated_source.id == "source-dwi"
            assert migrated_source.original_filename == "dwi.nii.gz"
            assert migrated_source.relative_path == "case-1/modalities/dwi.nii.gz"
            assert migrated_source.sha256 is None
            assert migrated_source.file_size is None
            migrated_job = connection.execute(
                text(
                    "select id, provider, status, provenance_json "
                    "from inference_jobs"
                )
            ).one()
            assert migrated_job.id == "inference-1"
            assert migrated_job.provider == "demo"
            assert migrated_job.status == "completed"
            assert migrated_job.provenance_json == '{"algorithm":"legacy-demo"}'
            migrated_segmentation = connection.execute(
                text(
                    "select id, inference_job_id, relative_path, "
                    "shape_x, shape_y, shape_z, spacing_x, spacing_y, spacing_z, "
                    "affine_json "
                    "from segmentation_artifacts"
                )
            ).one()
            assert migrated_segmentation.id == "inference-1"
            assert migrated_segmentation.inference_job_id == "inference-1"
            assert (
                migrated_segmentation.relative_path
                == "case-1/inference/segmentation.nii.gz"
            )
            assert (
                migrated_segmentation.shape_x,
                migrated_segmentation.shape_y,
                migrated_segmentation.shape_z,
            ) == (10, 11, 12)
            assert (
                migrated_segmentation.spacing_x,
                migrated_segmentation.spacing_y,
                migrated_segmentation.spacing_z,
            ) == (1.0, 1.1, 1.2)
            assert json.loads(migrated_segmentation.affine_json) == [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ]
            migrated_revision = connection.execute(
                text(
                    "select id, source_segmentation_id, relative_path "
                    "from annotation_revisions"
                )
            ).one()
            assert migrated_revision.id == "revision-1"
            assert migrated_revision.source_segmentation_id == "inference-1"
            assert migrated_revision.relative_path == "case-1/revisions/revision-1.nii.gz"
    finally:
        engine.dispose()


def test_migrated_mvp_sources_remain_listable_through_case_detail(
    tmp_path: Path,
    seed_mvp_db: Callable[[Path], Path],
) -> None:
    database_path = seed_mvp_db(tmp_path / "mvp.db")
    database_url = f"sqlite:///{database_path}"
    settings.data_dir = tmp_path / "data"
    configure_database(database_url)

    with TestClient(create_app(start_worker=False)) as client:
        response = client.get("/api/cases/case-1")

    assert response.status_code == 200
    assert response.json()["sources"] == [
        {
            "id": "source-adc",
            "modality": "ADC",
            "original_filename": "adc.nii.gz",
            "relative_path": "case-1/modalities/adc.nii.gz",
            "sha256": None,
            "file_size": None,
            "shape": [10, 11, 12],
            "spacing": [1.00005, 1.1, 1.2],
            "affine": [
                [1.00005, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            "datatype": None,
            "created_at": "2026-01-02T03:06:00",
        },
        {
            "id": "source-dwi",
            "modality": "DWI",
            "original_filename": "dwi.nii.gz",
            "relative_path": "case-1/modalities/dwi.nii.gz",
            "sha256": None,
            "file_size": None,
            "shape": [10, 11, 12],
            "spacing": [1.0, 1.1, 1.2],
            "affine": [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            "datatype": None,
            "created_at": "2026-01-02T03:05:00",
        },
        {
            "id": "source-flair",
            "modality": "FLAIR",
            "original_filename": "flair.nii.gz",
            "relative_path": "case-1/modalities/flair.nii.gz",
            "sha256": None,
            "file_size": None,
            "shape": [10, 11, 12],
            "spacing": [1.0, 1.1, 1.2],
            "affine": [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            "datatype": None,
            "created_at": "2026-01-02T03:07:00",
        },
    ]


def test_migrations_create_a_fresh_database_and_are_idempotent(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'fresh.db'}"

    run_migrations(database_url)
    run_migrations(database_url)

    engine = create_engine(database_url)
    try:
        assert {
            "cases",
            "source_artifacts",
            "inference_jobs",
            "segmentation_artifacts",
            "annotation_revisions",
            "exports",
            "alembic_version",
        } <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
