import hashlib
import io
import json
import zipfile
from queue import Queue
from threading import Event, Thread

import numpy as np
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ApiError
from app.core.release import RELEASE_VERSION
from app.db.models import AnnotationRevision, ExportArtifact, SourceArtifact
from app.db.session import new_session
from app.services import exports as exports_module
from app.services.exports import create_export
from app.services.inference.worker import InferenceWorker
from app.services.storage import Storage
from tests.helpers import import_case


def _completed_revision(client, tmp_path) -> tuple[str, str]:
    case_id = import_case(client, tmp_path)["id"]
    job = client.post(f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"}).json()
    assert InferenceWorker().run_once() is True
    segmentation_id = client.get(f"/api/inference-jobs/{job['id']}").json()["segmentation_id"]
    shape = (8, 8, 8)
    voxels = np.zeros(shape, dtype=np.uint8)
    voxels[1, 2, 3] = 1
    response = client.post(
        f"/api/cases/{case_id}/revisions",
        files={"voxels": ("labelmap.bin", voxels.reshape(-1, order="F").tobytes())},
        data={"shape": json.dumps(shape), "source_segmentation_id": segmentation_id},
    )
    assert response.status_code == 201, response.text
    return case_id, response.json()["id"]


def test_export_snapshots_saved_revision_with_portable_provenance_and_standard_bundle(
    client, tmp_path
) -> None:
    """Copying browser bytes, omitting either file, or leaking paths breaks this export contract."""
    case_id, revision_id = _completed_revision(client, tmp_path)

    response = client.post(f"/api/cases/{case_id}/exports", json={"revision_id": revision_id})

    assert response.status_code == 201, response.text
    export = response.json()
    mask = client.get(export["mask_url"])
    provenance_response = client.get(export["provenance_url"])
    bundle = client.get(export["bundle_url"])
    assert mask.status_code == provenance_response.status_code == bundle.status_code == 200
    provenance = provenance_response.json()
    digest = hashlib.sha256(mask.content).hexdigest()
    assert digest == export["mask_sha256"] == provenance["output"]["sha256"]
    assert provenance["software"]["version"] == RELEASE_VERSION
    assert provenance["ai_segmentation"]["service_version"] == RELEASE_VERSION
    assert provenance["annotation"]["lineage"] == [revision_id]
    assert "/home/" not in provenance_response.text
    assert provenance_response.content.endswith(b"\n")
    assert provenance_response.content.startswith(b'{\n  "ai_segmentation"')
    assert b"original_filename" not in provenance_response.content
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert set(archive.namelist()) == {"lesion-mask.nii.gz", "provenance.json"}
        assert archive.read("lesion-mask.nii.gz") == mask.content
        assert archive.read("provenance.json") == provenance_response.content


def test_export_lineage_follows_parent_pointers_not_revision_creation_order(
    client, tmp_path
) -> None:
    """Using global creation order instead of ancestry should fail this branch export."""
    case_id, root_id = _completed_revision(client, tmp_path)
    shape = (8, 8, 8)
    first = np.zeros(shape, dtype=np.uint8)
    first[0, 0, 0] = 1
    child = client.post(
        f"/api/cases/{case_id}/revisions",
        files={"voxels": ("labelmap.bin", first.reshape(-1, order="F").tobytes())},
        data={"shape": json.dumps(shape), "parent_revision_id": root_id},
    ).json()
    branch = np.zeros(shape, dtype=np.uint8)
    branch[1, 1, 1] = 1
    sibling = client.post(
        f"/api/cases/{case_id}/revisions",
        files={"voxels": ("labelmap.bin", branch.reshape(-1, order="F").tobytes())},
        data={"shape": json.dumps(shape), "parent_revision_id": root_id},
    ).json()
    export = client.post(f"/api/cases/{case_id}/exports", json={"revision_id": child["id"]}).json()

    assert sibling["id"] not in client.get(export["provenance_url"]).json()["annotation"]["lineage"]
    assert client.get(export["provenance_url"]).json()["annotation"]["lineage"] == [
        root_id,
        child["id"],
    ]


def test_export_rejects_missing_required_legacy_metadata_without_publishing(
    client, tmp_path
) -> None:
    """Allowing a null source hash would produce unverifiable provenance."""
    case_id, revision_id = _completed_revision(client, tmp_path)
    with new_session() as session:
        source = session.scalar(
            select(SourceArtifact).where(SourceArtifact.case_id == case_id)
        )
        assert source is not None
        source.sha256 = None
        session.commit()

    response = client.post(f"/api/cases/{case_id}/exports", json={"revision_id": revision_id})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "incomplete_provenance"
    with new_session() as session:
        assert session.scalar(select(ExportArtifact)) is None


def test_export_rejects_a_revision_from_another_case(client, tmp_path) -> None:
    """Dropping case ownership validation would permit cross-case export."""
    _case_id, revision_id = _completed_revision(client, tmp_path)
    other_case, _ = _completed_revision(client, tmp_path)

    response = client.post(f"/api/cases/{other_case}/exports", json={"revision_id": revision_id})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "revision_not_found"


def test_export_rejects_missing_lineage_parent_without_publishing(client, tmp_path) -> None:
    """Silently ending ancestry at a missing parent would create false provenance."""
    case_id, revision_id = _completed_revision(client, tmp_path)
    with new_session() as session:
        revision = session.get(AnnotationRevision, revision_id)
        assert revision is not None
        revision.parent_revision_id = "missing-parent"
        session.commit()

    response = client.post(f"/api/cases/{case_id}/exports", json={"revision_id": revision_id})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_revision_lineage"
    with new_session() as session:
        assert session.scalar(select(ExportArtifact)) is None


def test_export_never_replaces_destination_created_during_publication(
    client, tmp_path, monkeypatch
) -> None:
    """Replacing a directory that appears after preparation would destroy another snapshot."""
    case_id, revision_id = _completed_revision(client, tmp_path)
    export_id = "race-export"
    monkeypatch.setattr(exports_module, "new_uuid", lambda: export_id)
    original_copyfile = exports_module.shutil.copyfile
    copy_started = Event()
    continue_export = Event()

    def pause_after_copy(source, destination):
        copied = original_copyfile(source, destination)
        copy_started.set()
        assert continue_export.wait(timeout=3)
        return copied

    monkeypatch.setattr(exports_module.shutil, "copyfile", pause_after_copy)
    outcome: Queue[Exception | None] = Queue()

    def create_in_thread() -> None:
        try:
            with new_session() as session:
                create_export(session, Storage(settings.data_dir), case_id, revision_id)
        except Exception as exc:  # The thread communicates the service boundary result.
            outcome.put(exc)
        else:
            outcome.put(None)

    worker = Thread(target=create_in_thread)
    worker.start()
    assert copy_started.wait(timeout=3)
    destination = settings.data_dir / "exports" / export_id
    destination.mkdir()
    sentinel = destination / "existing-snapshot"
    sentinel.write_bytes(b"preserve me")
    continue_export.set()
    worker.join(timeout=3)

    error = outcome.get_nowait()
    assert isinstance(error, ApiError)
    assert error.code == "export_path_exists"
    assert sentinel.read_bytes() == b"preserve me"
    assert set(path.name for path in destination.iterdir()) == {"existing-snapshot"}
    with new_session() as session:
        assert session.scalar(select(ExportArtifact)) is None
