import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AnnotationRevision, SegmentationArtifact, SourceArtifact
from app.db.session import new_session
from app.services.nifti_codec import load_volume
from app.services.nifti_codec import save_volume as write_nifti
from app.services.revisions import compute_revision_stats
from tests.helpers import create_case, upload_case_modalities


def _prepare_completed_segmentation(
    client,
    tmp_path: Path,
    shape: tuple[int, int, int] = (4, 4, 4),
    affine: np.ndarray | None = None,
    header_spacing: tuple[float, float, float] | None = None,
) -> tuple[str, SegmentationArtifact]:
    case_id = create_case(client)["id"]
    if affine is None:
        upload_case_modalities(client, tmp_path, case_id, shape)
    else:
        for modality in ("DWI", "ADC", "FLAIR"):
            path = tmp_path / f"{modality.lower()}.nii.gz"
            data = np.zeros(shape, dtype=np.float32)
            data[1:3, 1:3, :] = 2 if modality == "DWI" else 1
            if header_spacing is None:
                write_nifti(path, data, affine, dtype=np.float32)
            else:
                _write_nifti_with_header_spacing(
                    path,
                    data,
                    affine,
                    header_spacing,
                    np.float32,
                )
            response = client.post(
                f"/api/cases/{case_id}/modalities/{modality}",
                files={"file": (path.name, path.read_bytes(), "application/gzip")},
            )
            assert response.status_code == 201, response.text
    run = client.post(f"/api/cases/{case_id}/segment")
    assert run.status_code == 201, run.text
    with new_session() as session:
        segmentation = session.get(SegmentationArtifact, run.json()["id"])
        assert segmentation is not None
        session.expunge(segmentation)
    return case_id, segmentation


def _write_nifti_with_header_spacing(
    path: Path,
    data: np.ndarray,
    affine: np.ndarray,
    spacing: tuple[float, float, float],
    dtype: type[np.generic],
) -> None:
    image = nib.Nifti1Image(np.asarray(data, dtype=dtype), affine)
    image.header.set_data_dtype(dtype)
    image.header.set_zooms(spacing)
    nib.save(image, str(path))


def _save_revision(
    client,
    case_id: str,
    mask: np.ndarray,
    **base: str,
):
    return client.post(
        f"/api/cases/{case_id}/revisions",
        files={
            "voxels": (
                "labelmap.bin",
                mask.astype(np.uint8).reshape(-1, order="F").tobytes(),
                "application/octet-stream",
            )
        },
        data={"shape": json.dumps(mask.shape), **base},
    )


def test_revision_stats_compare_parent_and_current() -> None:
    parent = np.array([0, 1, 1, 0], dtype=np.uint8)
    current = np.array([1, 1, 0, 0], dtype=np.uint8)

    stats = compute_revision_stats(parent, current, voxel_volume_mm3=2.0)

    assert stats.added_voxels == 1
    assert stats.removed_voxels == 1
    assert stats.changed_voxels == 2
    assert stats.lesion_voxels == 2
    assert stats.lesion_volume_ml == pytest.approx(0.004)


def test_first_revision_is_dwi_canonical_binary_and_measured(
    client,
    tmp_path: Path,
) -> None:
    shape = (4, 4, 4)
    dwi_affine = np.diag((1.25, 2.5, 3.75, 1.0))
    case_id, segmentation = _prepare_completed_segmentation(
        client,
        tmp_path,
        shape,
        dwi_affine,
    )
    base_path = settings.data_dir / segmentation.relative_path
    base = load_volume(base_path).data.astype(np.uint8)
    current = base.copy()
    lesion_voxel = tuple(np.argwhere(base == 1)[0])
    background_voxel = tuple(np.argwhere(base == 0)[0])
    current[lesion_voxel] = 0
    current[background_voxel] = 7

    response = client.post(
        f"/api/cases/{case_id}/revisions",
        files={
            "voxels": (
                "labelmap.bin",
                current.reshape(-1, order="F").tobytes(),
                "application/octet-stream",
            )
        },
        data={
            "shape": json.dumps(shape),
            "source_segmentation_id": segmentation.id,
            "note": "measured edit",
        },
    )

    assert response.status_code == 201, response.text
    revision = response.json()
    assert revision["parent_revision_id"] is None
    assert revision["source_segmentation_id"] == segmentation.id
    assert revision["edit_stats"] == {
        "added_voxels": 1,
        "removed_voxels": 1,
        "changed_voxels": 2,
        "lesion_voxels": int(np.count_nonzero(base)),
        "lesion_volume_ml": pytest.approx(
            float(np.count_nonzero(base)) * 1.25 * 2.5 * 3.75 / 1000
        ),
    }
    assert len(revision["sha256"]) == 64

    saved_response = client.get(
        f"/api/cases/{case_id}/revisions/{revision['id']}/file.nii.gz"
    )
    canonical_response = client.get(f"/api/revisions/{revision['id']}/file.nii.gz")
    assert canonical_response.status_code == 200
    assert canonical_response.content == saved_response.content
    saved_path = tmp_path / "saved-revision.nii.gz"
    saved_path.write_bytes(saved_response.content)
    saved = load_volume(saved_path)
    assert saved.datatype == "uint8"
    assert set(np.unique(saved.data)) == {0.0, 1.0}
    np.testing.assert_allclose(saved.affine, dwi_affine, atol=1e-5, rtol=0)
    assert saved.spacing == pytest.approx((1.25, 2.5, 3.75))


def test_later_revision_uses_immediate_parent_and_keeps_lineage_root(
    client,
    tmp_path: Path,
) -> None:
    case_id, segmentation = _prepare_completed_segmentation(client, tmp_path)
    base = load_volume(settings.data_dir / segmentation.relative_path).data.astype(np.uint8)
    first_mask = base.copy()
    first_added = tuple(np.argwhere(base == 0)[0])
    first_mask[first_added] = 1
    first_response = _save_revision(
        client,
        case_id,
        first_mask,
        source_segmentation_id=segmentation.id,
    )
    assert first_response.status_code == 201, first_response.text
    first = first_response.json()

    second_mask = first_mask.copy()
    second_added = tuple(np.argwhere(first_mask == 0)[0])
    second_mask[second_added] = 1
    second_response = _save_revision(
        client,
        case_id,
        second_mask,
        parent_revision_id=first["id"],
    )

    assert second_response.status_code == 201, second_response.text
    second = second_response.json()
    assert second["parent_revision_id"] == first["id"]
    assert second["source_segmentation_id"] == segmentation.id
    assert second["edit_stats"]["added_voxels"] == 1
    assert second["edit_stats"]["removed_voxels"] == 0
    assert second["edit_stats"]["changed_voxels"] == 1
    assert second["edit_stats"]["lesion_voxels"] == int(np.count_nonzero(base)) + 2


def test_revision_publish_never_overwrites_a_colliding_artifact(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id, segmentation = _prepare_completed_segmentation(client, tmp_path)
    mask = load_volume(settings.data_dir / segmentation.relative_path).data
    collision = settings.data_dir / "cases" / case_id / "revisions" / "collision.nii.gz"
    collision.parent.mkdir(parents=True)
    sentinel = b"existing immutable revision"
    real_save_volume = write_nifti

    monkeypatch.setattr(
        "app.services.revisions.Storage.revision_path",
        lambda _storage, _case_id: collision,
    )

    def save_then_collide(*args, **kwargs):
        result = real_save_volume(*args, **kwargs)
        collision.write_bytes(sentinel)
        return result

    monkeypatch.setattr("app.services.revisions.save_volume", save_then_collide)

    with pytest.raises(FileExistsError):
        _save_revision(
            client,
            case_id,
            mask,
            source_segmentation_id=segmentation.id,
        )

    assert collision.read_bytes() == sentinel
    with new_session() as session:
        assert session.scalar(select(AnnotationRevision)) is None


def test_database_failure_removes_published_revision_and_row(
    client,
    tmp_path: Path,
) -> None:
    case_id, segmentation = _prepare_completed_segmentation(client, tmp_path)
    mask = load_volume(settings.data_dir / segmentation.relative_path).data

    def fail_revision_commit(session, _flush_context, _instances) -> None:
        if any(isinstance(item, AnnotationRevision) for item in session.new):
            raise SQLAlchemyError("database failure")

    event.listen(Session, "before_flush", fail_revision_commit)
    try:
        with pytest.raises(SQLAlchemyError, match="database failure"):
            _save_revision(
                client,
                case_id,
                mask,
                source_segmentation_id=segmentation.id,
            )
    finally:
        event.remove(Session, "before_flush", fail_revision_commit)

    with new_session() as session:
        assert session.scalar(select(AnnotationRevision)) is None
    revision_dir = settings.data_dir / "cases" / case_id / "revisions"
    assert not list(revision_dir.glob("*.nii.gz"))


def test_atomic_rename_failure_leaves_no_revision_artifact_or_row(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id, segmentation = _prepare_completed_segmentation(client, tmp_path)
    mask = load_volume(settings.data_dir / segmentation.relative_path).data

    def fail_rename(_source: Path, _destination: Path) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr("app.services.revisions.os.replace", fail_rename)

    with pytest.raises(OSError, match="simulated rename failure"):
        _save_revision(
            client,
            case_id,
            mask,
            source_segmentation_id=segmentation.id,
        )

    with new_session() as session:
        assert session.scalar(select(AnnotationRevision)) is None
    revision_dir = settings.data_dir / "cases" / case_id / "revisions"
    assert not list(revision_dir.glob("*.nii.gz"))


def test_revision_preserves_dwi_header_spacing_and_uses_it_for_volume(
    client,
    tmp_path: Path,
) -> None:
    shape = (4, 4, 4)
    affine = np.eye(4)
    dwi_spacing = (2.0, 3.0, 4.0)
    case_id, segmentation = _prepare_completed_segmentation(
        client,
        tmp_path,
        shape,
        affine,
        dwi_spacing,
    )
    base_path = settings.data_dir / segmentation.relative_path
    base = load_volume(base_path).data.astype(np.uint8)
    _write_nifti_with_header_spacing(
        base_path,
        base,
        affine,
        dwi_spacing,
        np.uint8,
    )
    with new_session() as session:
        dwi = session.scalar(
            select(SourceArtifact).where(
                SourceArtifact.case_id == case_id,
                SourceArtifact.modality == "DWI",
            )
        )
        assert dwi is not None
        dwi_path = settings.data_dir / dwi.relative_path

    source = load_volume(dwi_path)
    assert source.spacing == pytest.approx(dwi_spacing)
    np.testing.assert_allclose(source.affine, affine, atol=1e-5, rtol=0)

    response = _save_revision(
        client,
        case_id,
        base,
        source_segmentation_id=segmentation.id,
    )

    assert response.status_code == 201, response.text
    revision = response.json()
    expected_volume_ml = float(np.count_nonzero(base)) * 24.0 / 1000.0
    assert revision["edit_stats"]["lesion_volume_ml"] == pytest.approx(
        expected_volume_ml
    )
    saved_response = client.get(f"/api/revisions/{revision['id']}/file.nii.gz")
    saved_path = tmp_path / "spacing-preserved.nii.gz"
    saved_path.write_bytes(saved_response.content)
    saved = load_volume(saved_path)
    assert saved.spacing == pytest.approx(dwi_spacing)
    np.testing.assert_allclose(saved.affine, affine, atol=1e-5, rtol=0)


def test_revision_rejects_base_spacing_that_differs_from_dwi(
    client,
    tmp_path: Path,
) -> None:
    case_id, segmentation = _prepare_completed_segmentation(
        client,
        tmp_path,
        affine=np.eye(4),
        header_spacing=(2.0, 3.0, 4.0),
    )
    base = load_volume(settings.data_dir / segmentation.relative_path)
    assert base.spacing == pytest.approx((1.0, 1.0, 1.0))

    response = _save_revision(
        client,
        case_id,
        base.data,
        source_segmentation_id=segmentation.id,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "incompatible_geometry"
    with new_session() as session:
        assert session.scalar(select(AnnotationRevision)) is None
