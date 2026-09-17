# NeuroAnnotate v1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the working MVP into NeuroAnnotate v1.0: a reproducible, self-hosted ischemic-stroke MRI annotation tool with atomic DWI/ADC/FLAIR import, persistent async segmentation jobs, immutable revision history, provenance-rich export, and optional DeepISLES GPU inference.

**Architecture:** Keep React + Cornerstone3D, FastAPI, SQLAlchemy/SQLite, local NIfTI storage, and Docker Compose. Introduce explicit source-artifact, inference-job, segmentation, revision, and export resources; migrate the existing database with Alembic; keep demo inference as the default CPU path; put real DeepISLES behind a private HTTP service started only by the Compose `gpu` profile.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Pydantic, NiBabel, NumPy, SciPy, httpx, jsonschema, pytest, React 19, TypeScript, Vite, Zustand, Cornerstone3D 5, Vitest, Docker Compose, NVIDIA Container Toolkit, DeepISLES.

**Spec:** `docs/superpowers/specs/2026-09-17-neuroannotate-v1-design.md`

## Global Constraints

- Research software only; no diagnostic, treatment, clinical-decision, or medical-device claims.
- v1.0 remains single-user, local/self-hosted, and NIfTI-only.
- A real-model case consists of exactly one immutable DWI, ADC, and FLAIR source artifact.
- DWI native geometry is the canonical lesion-mask geometry for AI segmentations, revisions, and exports.
- SHA-256 is mandatory for source NIfTIs, AI masks, revision masks, and exported masks.
- Portable provenance must not include absolute host paths or original uploaded filenames.
- `docker compose up` must remain usable without an NVIDIA GPU and must use the deterministic demo provider.
- `docker compose --profile gpu up` adds DeepISLES.
- Preserve the existing `.nii.gz` URL fix, Cornerstone streaming-volume load wait helper, and Vite Node polyfills.
- Hosted CI is CPU-only and must not download DeepISLES weights.
- DeepISLES source is pinned to commit `7658b608fc0d890cf14448ff3e58c47ad5c761e7` from `ezequieldlrosa/DeepIsles` (Apache-2.0).
- DeepISLES weights are downloaded from Zenodo record `14026715`, file `stroke_ensemble_weights.7z`, MD5 `be5b6dfcd66b55c2e6dc6db9a5880f7f`; weights must never be committed.
- NeuroAnnotate's DeepISLES defaults are `skull_strip=False`, `fast=False`, `save_team_outputs=False`, `results_mni=False`, `parallelize=True`.
- Each implementation task follows TDD: failing test -> verify failure -> minimal implementation -> focused pass -> broader verification -> commit.
- Execute in an isolated feature worktree created with `superpowers:using-git-worktrees`; do not implement in the user's active `main` checkout.

---

## Task 1: Add Alembic and the v1 Database Model

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_v1_schema.py`
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/test_migrations.py`
- Create: `backend/tests/fixtures/mvp_schema.sql`

**Interfaces:**
- Produces ORM classes `Case`, `SourceArtifact`, `InferenceJob`, `SegmentationArtifact`, `AnnotationRevision`, `ExportArtifact`.
- Produces `run_migrations(database_url: str) -> None`.

- [ ] **Step 1: Write the failing migration test**

Create a SQL fixture matching the current MVP schema (`cases`, `modalities`, `inference_runs`, `annotation_revisions`) and seed one row of each logical entity.

```python
# backend/tests/test_migrations.py
from sqlalchemy import create_engine, inspect, text
from app.db.session import run_migrations


def test_mvp_database_migrates_without_losing_case(tmp_path, seed_mvp_db):
    db = seed_mvp_db(tmp_path / "mvp.db")
    run_migrations(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")
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
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from cases")).scalar_one() == 1
        assert conn.execute(text("select count(*) from source_artifacts")).scalar_one() == 3
        assert conn.execute(text("select count(*) from annotation_revisions")).scalar_one() == 1
```

- [ ] **Step 2: Run the test and confirm failure**

```bash
cd backend
pytest tests/test_migrations.py -v
```
Expected: failure because Alembic and `run_migrations` are not present.

- [ ] **Step 3: Add dependencies**

Add to `backend/pyproject.toml` runtime dependencies:

```toml
alembic = ">=1.13,<2"
httpx = ">=0.27,<1"
jsonschema = ">=4.23,<5"
```

- [ ] **Step 4: Replace the ORM model set with explicit v1 entities**

Use these required fields and relationships in `backend/app/db/models.py`:

```python
class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    __table_args__ = (UniqueConstraint("case_id", "modality"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
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
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
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

class SegmentationArtifact(Base):
    __tablename__ = "segmentation_artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    inference_job_id: Mapped[str] = mapped_column(ForeignKey("inference_jobs.id", ondelete="CASCADE"), unique=True)
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

class AnnotationRevision(Base):
    __tablename__ = "annotation_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    parent_revision_id: Mapped[str | None] = mapped_column(ForeignKey("annotation_revisions.id"), nullable=True)
    source_segmentation_id: Mapped[str] = mapped_column(ForeignKey("segmentation_artifacts.id"))
    relative_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    edit_stats_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ExportArtifact(Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("annotation_revisions.id"), index=True)
    mask_path: Mapped[str] = mapped_column(String(500))
    provenance_path: Mapped[str] = mapped_column(String(500))
    mask_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

- [ ] **Step 5: Implement the migration**

The migration must create the v1 tables, copy `modalities` into `source_artifacts`, copy `inference_runs` into `inference_jobs`, create a paired `segmentation_artifacts` row for each migrated completed inference, translate `annotation_revisions.source_inference_id` into `source_segmentation_id`, preserve case/revision IDs and paths where possible, and create empty `exports`.

Legacy rows may have `sha256`, `file_size`, or `datatype` as null after migration. New rows must populate them. Export code in later tasks must reject legacy rows until backfill succeeds.

- [ ] **Step 6: Implement migration startup**

```python
def run_migrations(database_url: str) -> None:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
```

Use this as the normal startup upgrade path rather than `Base.metadata.create_all()`.

- [ ] **Step 7: Verify**

```bash
pytest tests/test_migrations.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 8: Commit**

```bash
git add backend/alembic.ini backend/alembic backend/app/db backend/pyproject.toml backend/tests/test_migrations.py backend/tests/fixtures/mvp_schema.sql
git commit -m "feat: add v1 database migrations"
```

---

## Task 2: Add Immutable Artifact Handling and Atomic Triad Import

**Files:**
- Create: `backend/app/services/checksums.py`
- Create: `backend/app/services/artifacts.py`
- Create: `backend/app/services/geometry.py`
- Modify: `backend/app/services/nifti.py`
- Modify: `backend/app/services/storage.py`
- Modify: `backend/app/services/cases.py`
- Modify: `backend/app/api/routes/cases.py`
- Modify: `backend/app/schemas/cases.py`
- Modify: `backend/app/repositories/cases.py`
- Create: `backend/tests/test_artifacts.py`
- Create: `backend/tests/test_case_import.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class NiftiMetadata:
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    affine: list[list[float]]
    datatype: str
    file_size: int

def sha256_file(path: Path) -> str: ...
def validate_source_nifti(path: Path) -> NiftiMetadata: ...
def same_geometry(a: NiftiMetadata, b: NiftiMetadata, *, atol: float = 1e-5) -> bool: ...
def import_case_triad(session: Session, storage: Storage, name: str, uploads: dict[str, UploadFile]) -> Case: ...
```

- [ ] **Step 1: Write failing checksum and validation tests**

```python
def test_sha256_file_is_stable(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"neuroannotate")
    assert sha256_file(p) == "e709fc9c1dc7fd898d8c3de43818e5662be4bd3aa6aa3b6bf32457ae3b3cda91"


def test_source_validation_allows_different_reference_geometry(tmp_path):
    dwi = write_test_nifti(tmp_path / "dwi.nii.gz", shape=(16, 16, 8), spacing=(1, 1, 2))
    flair = write_test_nifti(tmp_path / "flair.nii.gz", shape=(20, 20, 10), spacing=(1.2, 1.2, 3))
    assert validate_source_nifti(dwi).shape == (16, 16, 8)
    assert validate_source_nifti(flair).shape == (20, 20, 10)
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_artifacts.py -v
```

- [ ] **Step 3: Implement validation and geometry helpers**

`validate_source_nifti()` must reject unreadable files, non-3D volumes, zero dimensions, non-finite affine entries, and non-numeric datatypes with `ApiError(422, ...)`. `same_geometry()` must compare shape exactly and affine with `np.allclose(..., atol=1e-5, rtol=0)`.

- [ ] **Step 4: Write failing atomic-import API test**

```python
def test_case_creation_rolls_back_if_flair_is_invalid(client, sample_nifti_bytes):
    response = client.post(
        "/api/cases",
        data={"name": "Case A"},
        files={
            "dwi": ("dwi.nii.gz", sample_nifti_bytes, "application/gzip"),
            "adc": ("adc.nii.gz", sample_nifti_bytes, "application/gzip"),
            "flair": ("flair.nii.gz", b"invalid", "application/gzip"),
        },
    )
    assert response.status_code == 422
    assert client.get("/api/cases").json() == []
```

- [ ] **Step 5: Run and confirm failure**

```bash
pytest tests/test_case_import.py -v
```

- [ ] **Step 6: Implement staging and transaction**

Use `data/.staging/<uuid>/` for incoming files. Validate all three, calculate metadata and SHA-256, create `data/cases/<case-id>/source/`, atomically `os.replace()` the staged files into `dwi.nii.gz`, `adc.nii.gz`, `flair.nii.gz`, then commit one `Case` and three `SourceArtifact` rows in one DB transaction. On error: rollback and delete staging plus any uncommitted final case directory.

- [ ] **Step 7: Replace normal case creation with multipart triad import**

```python
@router.post("", response_model=CaseDetail, status_code=201)
def create_case(
    name: Annotated[str, Form(...)],
    dwi: Annotated[UploadFile, File(...)],
    adc: Annotated[UploadFile, File(...)],
    flair: Annotated[UploadFile, File(...)],
    session: Session = Depends(get_session),
) -> CaseDetail:
    return CaseDetail.from_orm(import_case_triad(session, Storage(settings.data_dir), name, {
        "DWI": dwi,
        "ADC": adc,
        "FLAIR": flair,
    }))
```

- [ ] **Step 8: Verify**

```bash
pytest tests/test_artifacts.py tests/test_case_import.py tests/test_cases.py tests/test_modalities.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests/test_artifacts.py backend/tests/test_case_import.py
git commit -m "feat: add atomic immutable case import"
```

---

## Task 3: Add Persistent Async Inference Jobs and the Demo Worker

**Files:**
- Create: `backend/app/services/inference/jobs.py`
- Create: `backend/app/services/inference/worker.py`
- Create: `backend/app/api/routes/inference_jobs.py`
- Modify: `backend/app/services/inference/base.py`
- Modify: `backend/app/services/inference/demo.py`
- Modify: `backend/app/services/inference/registry.py`
- Modify: `backend/app/api/routes/segmentations.py`
- Modify: `backend/app/schemas/inference.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_inference_jobs.py`
- Create: `backend/tests/test_job_recovery.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ProviderInfo:
    name: str
    model_name: str
    model_version: str
    service_version: str
    available: bool

@dataclass(frozen=True)
class ProviderResult:
    mask_path: Path
    provider: str
    model_name: str
    model_version: str
    service_version: str
    configuration: dict[str, object]
    runtime: dict[str, object]

class SegmentationProvider(Protocol):
    name: str
    def info(self) -> ProviderInfo: ...
    def segment(self, case: CaseInput, output_path: Path) -> ProviderResult: ...
```

- [ ] **Step 1: Write failing lifecycle test**

```python
def test_demo_job_moves_queued_to_completed(client, worker):
    case_id = create_valid_case(client)
    queued = client.post(
        f"/api/cases/{case_id}/inference-jobs",
        json={"provider": "demo"},
    ).json()
    assert queued["status"] == "queued"
    worker.run_once()
    done = client.get(f"/api/inference-jobs/{queued['id']}").json()
    assert done["status"] == "completed"
    assert done["segmentation_id"]
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_inference_jobs.py -v
```

- [ ] **Step 3: Implement job state rules**

```python
ALLOWED_TRANSITIONS = {
    "queued": {"running", "failed"},
    "running": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}
```

Clients cannot set status directly.

- [ ] **Step 4: Implement `InferenceWorker.run_once()`**

The worker must claim the oldest queued job, set it running, resolve source paths, call the provider, validate the returned mask against DWI geometry, atomically persist `inference/<job-id>/segmentation.nii.gz`, calculate SHA-256, create `SegmentationArtifact`, persist provider/config/runtime metadata, then mark completed. Any exception marks the job failed with one of: `provider_unavailable`, `provider_runtime_failure`, `invalid_model_output`, `input_validation_failure`, `application_interrupted`, `artifact_persistence_failure`.

- [ ] **Step 5: Add restart recovery test**

```python
def test_running_jobs_fail_on_backend_restart(session):
    job = seed_inference_job(session, status="running")
    recover_interrupted_jobs(session)
    session.refresh(job)
    assert job.status == "failed"
    assert job.failure_category == "application_interrupted"
```

- [ ] **Step 6: Run a single background worker from FastAPI lifespan**

Use one `threading.Thread` plus `threading.Event`. Production loop processes one queued job at a time; tests call `run_once()` directly.

- [ ] **Step 7: Add API resources**

```text
POST /api/cases/{case_id}/inference-jobs      -> 202
GET  /api/cases/{case_id}/inference-jobs
GET  /api/inference-jobs/{job_id}
POST /api/inference-jobs/{job_id}/retry       -> new queued job
GET  /api/segmentations/{segmentation_id}/file.nii.gz
```

- [ ] **Step 8: Verify**

```bash
pytest tests/test_inference_jobs.py tests/test_job_recovery.py tests/test_inference.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests/test_inference_jobs.py backend/tests/test_job_recovery.py
git commit -m "feat: add persistent inference jobs"
```

---

## Task 4: Make Revisions DWI-Canonical, Immutable, and Measurable

**Files:**
- Modify: `backend/app/services/revisions.py`
- Modify: `backend/app/api/routes/revisions.py`
- Modify: `backend/app/schemas/revisions.py`
- Create: `backend/tests/test_revisions_v1.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class RevisionStats:
    added_voxels: int
    removed_voxels: int
    changed_voxels: int
    lesion_voxels: int
    lesion_volume_ml: float

def compute_revision_stats(parent: np.ndarray, current: np.ndarray, voxel_volume_mm3: float) -> RevisionStats: ...
```

- [ ] **Step 1: Write failing stats test**

```python
def test_revision_stats_compare_parent_and_current():
    parent = np.array([0, 1, 1, 0], dtype=np.uint8)
    current = np.array([1, 1, 0, 0], dtype=np.uint8)
    stats = compute_revision_stats(parent, current, voxel_volume_mm3=2.0)
    assert stats.added_voxels == 1
    assert stats.removed_voxels == 1
    assert stats.changed_voxels == 2
    assert stats.lesion_voxels == 2
    assert stats.lesion_volume_ml == pytest.approx(0.004)
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_revisions_v1.py -v
```

- [ ] **Step 3: Always validate against case DWI**

The revision service resolves DWI from `SourceArtifact(modality="DWI")`, reconstructs its `NiftiMetadata`, and rejects a browser labelmap whose shape does not match. Saved revision affine/spacing must come from DWI. Persist as binary `uint8`.

- [ ] **Step 4: Implement lineage**

First human revision: `parent_revision_id=None`, `source_segmentation_id=<loaded AI segmentation>`.
Later revision: `parent_revision_id=<loaded parent revision>`, same `source_segmentation_id` as its lineage root.

- [ ] **Step 5: Use failure-safe persistence**

Write temp -> validate -> compute stats -> SHA-256 -> atomic rename -> DB commit. On DB failure remove the newly written file. Never overwrite an existing revision.

- [ ] **Step 6: Verify**

```bash
pytest tests/test_revisions.py tests/test_revisions_v1.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/revisions.py backend/app/api/routes/revisions.py backend/app/schemas/revisions.py backend/tests/test_revisions_v1.py
git commit -m "feat: add immutable revision lineage"
```

---

## Task 5: Add Immutable Export Snapshots and Provenance JSON

**Files:**
- Create: `backend/app/services/provenance.py`
- Create: `backend/app/services/exports.py`
- Create: `backend/app/schemas/exports.py`
- Modify: `backend/app/api/routes/exports.py`
- Create: `backend/tests/fixtures/provenance_schema_v1.json`
- Create: `backend/tests/test_provenance.py`
- Create: `backend/tests/test_exports_v1.py`

**Interfaces:**

```python
def build_provenance(*, case, sources, job, segmentation, revision, export, software) -> dict[str, object]: ...
def create_export(session: Session, storage: Storage, case_id: str, revision_id: str) -> ExportArtifact: ...
```

- [ ] **Step 1: Write failing privacy/schema test**

```python
def test_provenance_is_portable(provenance):
    assert provenance["schema"] == "neuroannotate.provenance"
    assert provenance["schema_version"] == "1.0"
    assert provenance["case"]["annotation_space"] == "DWI"
    assert set(provenance["sources"]) == {"DWI", "ADC", "FLAIR"}
    text = json.dumps(provenance)
    assert "/home/" not in text
    assert "original_filename" not in text
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_provenance.py tests/test_exports_v1.py -v
```

- [ ] **Step 3: Implement the exact top-level document**

```python
{
    "schema": "neuroannotate.provenance",
    "schema_version": "1.0",
    "software": {...},
    "export": {...},
    "case": {"case_id": case.id, "annotation_space": "DWI"},
    "sources": {"DWI": {...}, "ADC": {...}, "FLAIR": {...}},
    "ai_segmentation": {...},
    "annotation": {...},
    "output": {...},
    "disclaimer": "Research software only. Not for diagnosis or clinical decision-making.",
}
```

Write JSON with `indent=2`, `sort_keys=True`, UTF-8, final newline. Validate against `provenance_schema_v1.json` before publishing the export.

- [ ] **Step 4: Implement export creation**

Create `exports/<export-id>/`, copy the selected revision bytes to `lesion-mask.nii.gz`, calculate its SHA-256, build/validate provenance, atomically write `provenance.json`, then create `ExportArtifact`. Reject export when required legacy hashes are null.

- [ ] **Step 5: Implement routes**

```text
POST /api/cases/{case_id}/exports     body: {"revision_id":"..."}
GET  /api/exports/{id}/mask
GET  /api/exports/{id}/provenance
GET  /api/exports/{id}/bundle
```

The ZIP contains exactly `lesion-mask.nii.gz` and `provenance.json`.

- [ ] **Step 6: Verify checksum identity**

Test that downloaded mask SHA-256 equals both `exports.mask_sha256` and `provenance.output.sha256`.

- [ ] **Step 7: Verify**

```bash
pytest tests/test_provenance.py tests/test_exports_v1.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/provenance.py backend/app/services/exports.py backend/app/schemas/exports.py backend/app/api/routes/exports.py backend/tests
git commit -m "feat: add provenance-rich exports"
```

---

## Task 6: Update Frontend Types, API Client, and Workspace State

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/state/workspace.ts`
- Modify: `frontend/tests/apiUrls.test.ts`
- Create: `frontend/tests/workspace.test.ts`

**Interfaces:**

```ts
export type InferenceStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface CaseDetail {
  id: string;
  name: string;
  annotation_space: 'DWI';
  sources: SourceArtifact[];
}

export interface InferenceJob {
  id: string;
  case_id: string;
  provider: string;
  status: InferenceStatus;
  segmentation_id: string | null;
  failure_category: string | null;
  error_message: string | null;
}

export interface ExportArtifact {
  id: string;
  revision_id: string;
  mask_sha256: string;
  mask_url: string;
  provenance_url: string;
  bundle_url: string;
}
```

- [ ] **Step 1: Write failing URL/store tests**

```ts
it('keeps a .nii.gz suffix for Cornerstone segmentation URLs', () => {
  expect(segmentationFileUrl('seg-1')).toMatch(/\/api\/segmentations\/seg-1\/file\.nii\.gz$/);
});

it('tracks annotation dirty state explicitly', () => {
  const store = createWorkspaceStore();
  store.getState().markDirty();
  expect(store.getState().dirty).toBe(true);
});
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd frontend
npm test -- --run tests/apiUrls.test.ts tests/workspace.test.ts
```

- [ ] **Step 3: Implement multipart atomic case client**

```ts
export async function createCase(input: { name: string; dwi: File; adc: File; flair: File }): Promise<CaseDetail> {
  const body = new FormData();
  body.set('name', input.name);
  body.set('dwi', input.dwi);
  body.set('adc', input.adc);
  body.set('flair', input.flair);
  return request('/api/cases', { method: 'POST', body });
}
```

- [ ] **Step 4: Add typed clients**

Implement create/list/get/retry inference jobs, list/save revisions, create/get exports, provider status, system health, and file URL helpers. Do not add WebSocket code.

- [ ] **Step 5: Expand workspace state**

State keys: `selectedCaseId`, `selectedModality`, `loadedSegmentationId`, `loadedRevisionId`, `baseRevisionId`, `dirty`, `activeJobId`. Do not store voxel arrays in Zustand.

- [ ] **Step 6: Verify**

```bash
npm test -- --run tests/apiUrls.test.ts tests/workspace.test.ts
npm run lint
npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/client.ts frontend/src/state/workspace.ts frontend/tests
git commit -m "feat: add v1 frontend API state"
```

---

## Task 7: Build the v1 Workflow UI

**Files:**
- Modify: `frontend/src/features/cases/CaseUploadPanel.tsx`
- Modify: `frontend/src/features/cases/CaseSidebar.tsx`
- Modify: `frontend/src/features/inference/InferenceControls.tsx`
- Modify: `frontend/src/features/annotation/AnnotationToolbar.tsx`
- Modify: `frontend/src/features/revisions/RevisionPanel.tsx`
- Create: `frontend/src/features/exports/ExportPanel.tsx`
- Create: `frontend/src/features/system/SystemStatus.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/tests/CaseUploadPanel.test.tsx`
- Modify: `frontend/tests/InferenceControls.test.tsx`
- Modify: `frontend/tests/RevisionPanel.test.tsx`
- Create: `frontend/tests/ExportPanel.test.tsx`
- Create: `frontend/tests/SystemStatus.test.tsx`

- [ ] **Step 1: Write failing case-form test**

Test that Create Case stays disabled until name + DWI + ADC + FLAIR are present and submits one `createCase()` call containing all four fields.

- [ ] **Step 2: Write failing inference-state tests**

Cover visible UI for queued, running, completed, failed. Retry is visible only for failed jobs. Demo mode must say that the demo provider is deterministic and is not a trained medical model.

- [ ] **Step 3: Write failing dirty-export test**

```ts
it('disables export while unsaved edits exist', () => {
  render(<ExportPanel revision={revision} dirty={true} />);
  expect(screen.getByRole('button', { name: /create export/i })).toBeDisabled();
  expect(screen.getByText(/save your annotation changes/i)).toBeInTheDocument();
});
```

- [ ] **Step 4: Run and confirm failures**

```bash
cd frontend
npm test -- --run tests/CaseUploadPanel.test.tsx tests/InferenceControls.test.tsx tests/RevisionPanel.test.tsx tests/ExportPanel.test.tsx tests/SystemStatus.test.tsx
```

- [ ] **Step 5: Implement case and empty states**

No cases: `No MRI cases yet` and `Create a case using DWI, ADC, and FLAIR NIfTI volumes.`
Mismatched ADC/FLAIR geometry is informational, not an import error.

- [ ] **Step 6: Implement 2-second inference polling**

Poll only while job status is `queued` or `running`, stop on completed/failed/unmount, and keep the browser request path through the FastAPI app rather than the GPU service.

- [ ] **Step 7: Implement annotation/revision controls**

Show base mask, opacity, Brush, Erase, Undo, Redo, brush size, unsaved change count, optional revision note, Save Revision. Clear dirty state only after successful server persistence.

- [ ] **Step 8: Implement revision timeline and export panel**

Timeline root is the AI segmentation. Revisions show timestamp, note, added/removed counts, and current selection. Editing an old revision displays its parent/base clearly. Export requires a saved revision and no dirty changes.

- [ ] **Step 9: Implement system status**

Report backend, storage, database, current inference mode, and DeepISLES availability. `not_enabled` is neutral in demo mode.

- [ ] **Step 10: Verify**

```bash
npm test -- --run
npm run lint
npm run build
```

- [ ] **Step 11: Commit**

```bash
git add frontend/src frontend/tests
git commit -m "feat: build v1 annotation workflow"
```

---

## Task 8: Enforce DWI-Canonical Overlay Safety

**Files:**
- Modify: `frontend/src/features/viewer/ViewerGrid.tsx`
- Modify: `frontend/src/cornerstone/segmentation.ts`
- Modify: `frontend/src/cornerstone/viewer.ts`
- Modify: `frontend/tests/ViewerGrid.test.tsx`
- Create: `frontend/tests/overlayGeometry.test.ts`

**Interfaces:**

```ts
export interface VolumeGeometry {
  shape: [number, number, number];
  affine: number[][];
}
export function canDisplaySegmentationOn(source: VolumeGeometry, dwi: VolumeGeometry): boolean;
```

- [ ] **Step 1: Write failing geometry-policy test**

```ts
it('shows DWI-space masks only on matching geometry', () => {
  expect(canDisplaySegmentationOn(dwi, dwi)).toBe(true);
  expect(canDisplaySegmentationOn(flairDifferentGeometry, dwi)).toBe(false);
});
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd frontend
npm test -- --run tests/overlayGeometry.test.ts tests/ViewerGrid.test.tsx
```

- [ ] **Step 3: Implement guard**

Shape must match exactly. Affine elements must differ by no more than `1e-5`. When blocked, remove/hide the segmentation representation and show `Segmentation overlay unavailable in this geometry.` Do not resample in the browser.

- [ ] **Step 4: Verify regression-sensitive viewer tests**

```bash
npm test -- --run tests/overlayGeometry.test.ts tests/ViewerGrid.test.tsx tests/volumeLoading.test.ts tests/apiUrls.test.ts
npm test -- --run
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/viewer/ViewerGrid.tsx frontend/src/cornerstone frontend/tests
git commit -m "feat: enforce DWI overlay geometry"
```

---

## Task 9: Add the DeepISLES HTTP Service and Backend Provider

**Files:**
- Create: `inference-service/Dockerfile`
- Create: `inference-service/requirements-service.txt`
- Create: `inference-service/app/__init__.py`
- Create: `inference-service/app/main.py`
- Create: `inference-service/app/runner.py`
- Create: `inference-service/app/metadata.py`
- Create: `inference-service/scripts/fetch_weights.sh`
- Create: `inference-service/tests/test_api_contract.py`
- Create: `backend/app/services/inference/deepisles.py`
- Modify: `backend/app/services/inference/registry.py`
- Create: `backend/tests/test_deepisles_provider.py`

**Service contract:**

```text
GET  /health
GET  /v1/info
POST /v1/segment   multipart: dwi, adc, flair
```

`POST /v1/segment` returns a ZIP with exactly `segmentation.nii.gz` and `metadata.json`.

- [ ] **Step 1: Write mock API contract tests**

Patch the runner so no real weights are required. Assert `/v1/info` identifies the service and pinned upstream commit. Assert `/v1/segment` accepts three multipart files and returns a ZIP with the two required entries.

- [ ] **Step 2: Run and confirm failure**

```bash
pytest inference-service/tests/test_api_contract.py -v
```

- [ ] **Step 3: Pin upstream source in Dockerfile**

```dockerfile
ARG DEEPISLES_COMMIT=7658b608fc0d890cf14448ff3e58c47ad5c761e7
RUN git clone https://github.com/ezequieldlrosa/DeepIsles.git /opt/deepisles \
 && cd /opt/deepisles \
 && git checkout "$DEEPISLES_COMMIT"
```

Match upstream's required Python 3.8 / PyTorch 1.11 / CUDA 11.3 environment rather than silently modernizing model dependencies.

- [ ] **Step 4: Implement weight fetch with integrity check**

```bash
#!/usr/bin/env bash
set -euo pipefail
url='https://zenodo.org/records/14026715/files/stroke_ensemble_weights.7z?download=1'
expected='be5b6dfcd66b55c2e6dc6db9a5880f7f'
mkdir -p /models
curl -fL "$url" -o /models/stroke_ensemble_weights.7z
echo "$expected  /models/stroke_ensemble_weights.7z" | md5sum -c -
7z x /models/stroke_ensemble_weights.7z -o/opt/deepisles -y
```

- [ ] **Step 5: Implement the ensemble runner**

```python
from src.isles22_ensemble import IslesEnsemble


def run_deepisles(dwi: Path, adc: Path, flair: Path, output_dir: Path) -> Path:
    model = IslesEnsemble()
    model.predict_ensemble(
        ensemble_path="/opt/deepisles",
        input_dwi_path=str(dwi),
        input_adc_path=str(adc),
        input_flair_path=str(flair),
        output_path=str(output_dir),
        skull_strip=False,
        fast=False,
        save_team_outputs=False,
        results_mni=False,
        parallelize=True,
    )
    final_mask = locate_final_ensemble_mask(output_dir)
    return final_mask
```

`locate_final_ensemble_mask()` must identify the final DeepISLES ensemble output deterministically from the pinned upstream output layout and raise a service error if zero or multiple candidate final masks are found.

- [ ] **Step 6: Implement backend provider**

Use `httpx.Client(timeout=None)` only inside the background worker. Upload DWI/ADC/FLAIR, unpack the returned ZIP into a temporary directory, parse `metadata.json`, and return `ProviderResult`. Connection errors map to `provider_unavailable`; non-2xx/service execution errors map to `provider_runtime_failure`.

- [ ] **Step 7: Verify contract tests**

```bash
cd backend && pytest tests/test_deepisles_provider.py -v
cd .. && pytest inference-service/tests/test_api_contract.py -v
```

- [ ] **Step 8: Commit**

```bash
git add inference-service backend/app/services/inference/deepisles.py backend/app/services/inference/registry.py backend/tests/test_deepisles_provider.py
git commit -m "feat: add DeepISLES service adapter"
```

---

## Task 10: Add GPU Compose Profile and Runtime Health

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `Makefile`
- Create: `scripts/validate_gpu.sh`
- Modify: `backend/app/api/routes/health.py`
- Modify: `backend/tests/test_health.py`

- [ ] **Step 1: Write failing health test**

```python
def test_health_is_ok_when_gpu_profile_is_not_enabled(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["inference"]["mode"] == "demo"
    assert body["inference"]["deepisles"] == "not_enabled"
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_health.py -v
```

- [ ] **Step 3: Add Compose `gpu` service**

Service name `deepisles`, profile `gpu`, private network only, `NEUROANNOTATE_DEEPISLES_URL=http://deepisles:8080`, NVIDIA device access, persistent model-cache volume, HTTP healthcheck. Default Compose must not require NVIDIA.

- [ ] **Step 4: Add `make` targets**

```make
migrate:
	cd backend && alembic upgrade head

validate-gpu:
	./scripts/validate_gpu.sh
```

- [ ] **Step 5: Implement `scripts/validate_gpu.sh`**

Require `NEUROANNOTATE_GPU_TEST_CASE` pointing to a licensed local directory containing `dwi.nii.gz`, `adc.nii.gz`, `flair.nii.gz`. Start GPU profile, wait for `/health`, verify `/v1/info` reports the pinned commit, create a NeuroAnnotate case, start a DeepISLES job, poll up to 30 minutes, save a no-op revision from the result, create an export, download it, and use NiBabel to assert the exported mask is binary and matches DWI shape/affine.

- [ ] **Step 6: Verify Compose and backend**

```bash
docker compose config >/dev/null
docker compose --profile gpu config >/dev/null
cd backend
pytest tests/test_health.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example Makefile scripts/validate_gpu.sh backend/app/api/routes/health.py backend/tests/test_health.py
git commit -m "feat: add optional GPU deployment"
```

---

## Task 11: Add Deterministic End-to-End Demo Coverage and CI

**Files:**
- Modify: `backend/app/scripts/generate_demo_data.py`
- Modify: `backend/app/scripts/seed_demo_case.py`
- Create: `backend/tests/test_v1_workflow.py`
- Modify: `scripts/smoke.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `Makefile`

- [ ] **Step 1: Write failing full-workflow test**

```python
def test_demo_path_reaches_reproducible_export(client, worker):
    case = create_case_from_generated_triad(client)
    job = client.post(f"/api/cases/{case['id']}/inference-jobs", json={"provider": "demo"}).json()
    worker.run_once()
    completed = client.get(f"/api/inference-jobs/{job['id']}").json()
    revision = save_noop_revision(client, case, completed)
    export = client.post(f"/api/cases/{case['id']}/exports", json={"revision_id": revision["id"]}).json()
    assert client.get(export["bundle_url"]).status_code == 200
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_v1_workflow.py -v
```

- [ ] **Step 3: Make synthetic data deterministic**

Use a fixed RNG seed, synthetic intensity fields, and fixed shape/spacing. The deterministic demo mask must also be reproducible from the same generated case. No patient data goes into Git.

- [ ] **Step 4: Expand HTTP smoke script**

`./scripts/smoke.sh` must perform health -> atomic triad import -> demo job -> poll -> segmentation -> revision -> export -> ZIP entry verification and print PASS only after all succeed.

- [ ] **Step 5: Expand CI**

Keep backend Ruff/pytest and frontend lint/tests/build. Add Alembic migration test and a lightweight Docker config job:

```yaml
- run: docker compose config >/dev/null
- run: docker compose --profile gpu config >/dev/null
```

Do not build the DeepISLES image or fetch weights in hosted CI.

- [ ] **Step 6: Add `make verify`**

```make
verify:
	cd backend && ruff check app tests && pytest -q
	cd frontend && npm run lint && npm test -- --run && npm run build
	docker compose config >/dev/null
	docker compose --profile gpu config >/dev/null
```

- [ ] **Step 7: Verify**

```bash
make verify
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/scripts backend/tests/test_v1_workflow.py scripts/smoke.sh .github/workflows/ci.yml Makefile
git commit -m "test: cover the v1 demo workflow"
```

---

## Task 12: Complete Research-Software Documentation and Release Metadata

**Files:**
- Create: `CHANGELOG.md`
- Create: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `CITATION.cff`
- Create: `SECURITY.md`
- Create: `AI_USAGE.md`
- Create: `docs/gpu.md`
- Create: `docs/workflow.md`
- Create: `docs/provenance.md`
- Create: `docs/troubleshooting.md`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/demo.md`
- Create: `backend/tests/test_docs_metadata.py`

- [ ] **Step 1: Write failing metadata test**

```python
def test_release_metadata_files_exist(repo_root):
    for rel in [
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "CITATION.cff",
        "SECURITY.md",
        "AI_USAGE.md",
        "docs/gpu.md",
        "docs/workflow.md",
        "docs/provenance.md",
        "docs/troubleshooting.md",
    ]:
        assert (repo_root / rel).is_file(), rel
```

Parse `CITATION.cff` in the same test and require title `NeuroAnnotate`, version `1.0.0`, and repository URL `https://github.com/sifat371/neuroannotate`.

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_docs_metadata.py -v
```

- [ ] **Step 3: Update README and architecture docs**

README order: description -> research-use disclaimer -> Quick Start -> GPU Quick Start -> workflow -> architecture -> testing/contributing -> citation -> license/third-party attribution. Remove wording that presents nnU-Net as the intended v1 real provider.

- [ ] **Step 4: Write GPU documentation**

Document NVIDIA Container Toolkit, the ~9.1 GB Zenodo weights, record/file/MD5, model-cache behavior, `docker compose --profile gpu up`, `make validate-gpu`, and common GPU/service/weights failures.

- [ ] **Step 5: Write provenance/privacy documentation**

Document each JSON section, SHA-256 semantics, DWI canonical space, excluded local-path/original-filename fields, and the fact that edit statistics are descriptive mask statistics rather than clinical metrics.

- [ ] **Step 6: Add AI usage disclosure**

`AI_USAGE.md` records that generative AI assisted architecture and implementation planning and, where used, code/documentation drafting; maintainers review and test accepted changes and retain responsibility for them.

- [ ] **Step 7: Verify**

```bash
cd backend && pytest tests/test_docs_metadata.py -v && pytest -q && ruff check app tests
cd ../frontend && npm run lint && npm test -- --run && npm run build
cd .. && docker compose config >/dev/null && docker compose --profile gpu config >/dev/null
```

- [ ] **Step 8: Commit**

```bash
git add README.md CHANGELOG.md CONTRIBUTING.md CODE_OF_CONDUCT.md CITATION.cff SECURITY.md AI_USAGE.md docs backend/tests/test_docs_metadata.py
git commit -m "docs: prepare NeuroAnnotate v1 release"
```

---

## Task 13: Final Release-Candidate Verification

**Files:**
- Modify only when a failing verification reveals a defect; every fix must add a regression test in the owning subsystem.

- [ ] **Step 1: Require a clean worktree**

```bash
git status --short
```
Expected: no output.

- [ ] **Step 2: Run backend gates**

```bash
cd backend
ruff check app tests
pytest -v
alembic upgrade head
alembic current
```

- [ ] **Step 3: Run frontend gates**

```bash
cd ../frontend
npm run lint
npm test -- --run
npm run build
```

- [ ] **Step 4: Run default Docker smoke**

```bash
cd ..
docker compose config >/dev/null
docker compose --profile gpu config >/dev/null
docker compose up -d --build
./scripts/smoke.sh
docker compose down
```

- [ ] **Step 5: Run a migration drill on a copy of a real MVP database**

Copy an existing pre-v1 `neuroannotate.db` to a temporary directory, point the backend to the copy, run Alembic, start the API, and verify the existing case/source/inference/revision records remain listable. Never run destructive migration experiments on the user's primary local database.

- [ ] **Step 6: Run real GPU validation before claiming GPU readiness**

```bash
NEUROANNOTATE_GPU_TEST_CASE=/absolute/path/to/licensed/test-case make validate-gpu
```

If no supported NVIDIA host plus licensed triad is available, GPU readiness remains an explicit release blocker; do not state that the DeepISLES path is validated.

- [ ] **Step 7: Check that no patient data or model weights are tracked**

```bash
git ls-files | grep -Ei '\.(nii|nii\.gz|7z|pt|pth|ckpt)$' || true
git status --short
git log --oneline --decorate -15
```
Only intentionally generated non-patient fixtures may appear.

- [ ] **Step 8: Open the implementation PR**

PR body must summarize atomic triad import, migration, async jobs, revision/provenance/export model, frontend workflow, optional DeepISLES GPU service, exact verification commands run, and the research-use-only disclaimer. Wait for CI and code review before merge.

---

## Self-Review

### Spec coverage
- Architecture and deployment: Tasks 3, 9, 10.
- Atomic immutable source triad and SHA-256: Task 2.
- DWI canonical mask geometry: Tasks 2, 4, 8, 9.
- Persistent async jobs, single worker, restart recovery, no automatic retry: Task 3.
- DeepISLES provider, pinned source, external weights: Tasks 9-10.
- Complete immutable revisions and lineage statistics: Task 4.
- NIfTI + provenance JSON + ZIP export: Task 5.
- Workflow UI and system/empty states: Tasks 6-8.
- Alembic preservation of MVP data: Tasks 1 and 13.
- Deterministic CPU CI and explicit GPU validation: Tasks 11 and 13.
- Research-software metadata and AI disclosure: Task 12.

### Interface consistency
- Inference status is always `queued | running | completed | failed`.
- `SegmentationArtifact.id` is the AI-mask identifier used by revisions.
- `AnnotationRevision.id` is the lineage/export identifier.
- Export consumes only a saved revision; never unsaved browser state.
- Demo and DeepISLES both return `ProviderResult`.
- Cornerstone-facing NIfTI URLs keep `.nii.gz` suffixes.

### Scope
This is one integrated release plan because all tasks converge on a single case -> job -> segmentation -> revision -> export workflow. The order intentionally completes the deterministic CPU path before real GPU integration so every checkpoint remains testable.