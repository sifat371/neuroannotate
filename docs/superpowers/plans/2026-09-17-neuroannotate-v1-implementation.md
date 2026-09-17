# NeuroAnnotate v1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the current NeuroAnnotate MVP into a reproducible v1.0 research-software release with atomic DWI/ADC/FLAIR case import, persistent asynchronous segmentation jobs, immutable revisions, provenance-rich exports, a polished workflow UI, and an optional DeepISLES GPU service.

**Architecture:** Keep the existing React + Cornerstone3D frontend, FastAPI backend, SQLAlchemy/SQLite persistence, local NIfTI storage, and Docker Compose workflow. Add explicit artifact/job/export resources and Alembic migrations on the application side, while isolating real DeepISLES inference behind a private HTTP GPU service. The deterministic demo path remains the CPU/default runtime and must support the same job/revision/export workflow as the real provider.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Pydantic, NiBabel, NumPy, SciPy, httpx, pytest, React 19, TypeScript, Vite, Zustand, Cornerstone3D 5, Vitest, Docker Compose, NVIDIA Container Toolkit, DeepISLES.

**Spec:** `docs/superpowers/specs/2026-09-17-neuroannotate-v1-design.md`

## Global Constraints

- Product positioning: research software only; never present NeuroAnnotate as a medical device or diagnostic/clinical decision-support tool.
- v1.0 is single-user, local/self-hosted, NIfTI-only, and focused on ischemic stroke lesion annotation.
- Real-model cases require DWI + ADC + FLAIR; DWI native space is canonical for AI masks, revisions, and exports.
- Source triads are immutable after case creation; changing the source triad means creating a new case.
- Scientifically meaningful artifacts use SHA-256: source NIfTIs, AI masks, revisions, and exported masks.
- Portable provenance must exclude absolute host paths and original uploaded filenames by default.
- Default `docker compose up` must remain CPU/lightweight and use the deterministic demo provider.
- `docker compose --profile gpu up` adds the DeepISLES service.
- Existing NIfTI `.nii.gz` URL suffix handling, Cornerstone streaming-volume wait logic, and Vite Node polyfills must not regress.
- Hosted CI remains CPU-only and must not download the 9.1 GB DeepISLES weights.
- DeepISLES source is pinned to upstream commit `7658b608fc0d890cf14448ff3e58c47ad5c761e7` (Apache-2.0). Its ensemble weights come from Zenodo record `14026715`, file `stroke_ensemble_weights.7z`, MD5 `be5b6dfcd66b55c2e6dc6db9a5880f7f`, and are never committed to this repository.
- DeepISLES runtime defaults for NeuroAnnotate v1.0: `skull_strip=False`, `fast=False`, `save_team_outputs=False`, `results_mni=False`, `parallelize=True`.
- Every task follows TDD: write a failing test, run it and observe the failure, implement the minimum change, run focused tests, then run the relevant broader suite before committing.
- Execute implementation in an isolated worktree/feature branch created with `superpowers:using-git-worktrees`; do not implement directly on the user's working `main` checkout.

---

## File Map

The implementation should preserve current file boundaries where they are already good and introduce new focused modules rather than growing route files into service monoliths.

### Backend persistence and migrations

- Create `backend/alembic.ini` — Alembic configuration.
- Create `backend/alembic/env.py` — migration environment bound to `app.db.models.Base`.
- Create `backend/alembic/versions/0001_v1_schema.py` — migration from current MVP tables to the v1 schema.
- Modify `backend/app/db/models.py` — v1 ORM models and relationships.
- Modify `backend/app/db/session.py` — run/validate migrations at startup instead of `create_all` as the upgrade mechanism.
- Modify `backend/pyproject.toml` — add Alembic, httpx, jsonschema dependencies.

### Backend artifacts, import, validation

- Create `backend/app/services/checksums.py` — streaming SHA-256 and MD5 helpers.
- Create `backend/app/services/artifacts.py` — immutable artifact metadata, atomic writes/moves, case paths.
- Create `backend/app/services/geometry.py` — DWI-space affine/shape comparison.
- Modify `backend/app/services/nifti.py` — source/mask validation and metadata extraction.
- Modify `backend/app/services/storage.py` — safe staging and atomic rename helpers.
- Modify `backend/app/services/cases.py` — transactional triad import orchestration.
- Modify `backend/app/api/routes/cases.py` — multipart atomic case creation and case detail.
- Keep `backend/app/api/routes/modalities.py` only as temporary compatibility API; the v1 UI must not call it.
- Modify `backend/app/schemas/cases.py` — richer case/source responses.
- Modify `backend/app/repositories/cases.py` — source/job/segmentation/revision/export persistence access.

### Backend inference

- Create `backend/app/services/inference/jobs.py` — job state transitions and recovery rules.
- Create `backend/app/services/inference/worker.py` — single local queue worker.
- Create `backend/app/services/inference/deepisles.py` — HTTP DeepISLES provider client.
- Modify `backend/app/services/inference/base.py` — provider protocol/result metadata.
- Modify `backend/app/services/inference/demo.py` — return a v1 provider result through the same contract.
- Modify `backend/app/services/inference/registry.py` — provider discovery/readiness.
- Create `backend/app/api/routes/inference_jobs.py` — create/list/get/retry job resources.
- Modify `backend/app/api/routes/segmentations.py` — serve by segmentation ID and retain compatibility aliases.
- Modify `backend/app/schemas/inference.py` — job/provider/segmentation schemas.
- Modify `backend/app/main.py` — worker lifecycle and interrupted-job recovery.

### Backend revisions and export

- Modify `backend/app/services/revisions.py` — DWI-space validation, parent linkage, edit statistics.
- Modify `backend/app/api/routes/revisions.py` — v1 revision semantics and file-by-ID route.
- Modify `backend/app/schemas/revisions.py` — parent/source/edit-stat fields.
- Create `backend/app/services/provenance.py` — deterministic provenance document builder.
- Create `backend/app/services/exports.py` — immutable mask + JSON export creation and ZIP streaming.
- Create `backend/app/schemas/exports.py` — export response model.
- Modify `backend/app/api/routes/exports.py` — create export, mask/provenance/bundle endpoints.

### DeepISLES service

- Create `inference-service/Dockerfile` — GPU runtime that pins upstream DeepISLES source commit and adds the NeuroAnnotate wrapper.
- Create `inference-service/requirements-service.txt` — FastAPI/Uvicorn wrapper dependencies layered onto the upstream environment.
- Create `inference-service/app/main.py` — `/health`, `/v1/info`, `/v1/segment`.
- Create `inference-service/app/runner.py` — `IslesEnsemble.predict_ensemble(...)` adapter.
- Create `inference-service/app/metadata.py` — engine/service/version metadata.
- Create `inference-service/scripts/fetch_weights.sh` — explicit Zenodo download + MD5 verification + extraction.
- Create `inference-service/tests/test_api_contract.py` — CPU/mock contract tests; no weights required.
- Modify `docker-compose.yml` — GPU profile and private network wiring.
- Modify `.env.example` — provider/service URL and model-cache configuration.

### Frontend

- Modify `frontend/src/types/api.ts` — v1 case/job/segmentation/revision/export/provider types.
- Modify `frontend/src/api/client.ts` — atomic case import, job polling APIs, export APIs, file URLs.
- Modify `frontend/src/state/workspace.ts` — selected case/modality/base mask/dirty/job/revision/export state.
- Modify `frontend/src/features/cases/CaseUploadPanel.tsx` — atomic triad import form.
- Modify `frontend/src/features/cases/CaseSidebar.tsx` — empty state and source readiness.
- Modify `frontend/src/features/inference/InferenceControls.tsx` — provider status and queued/running/completed/failed UI.
- Modify `frontend/src/features/annotation/AnnotationToolbar.tsx` — dirty/edit stats, shortcuts, save revision.
- Modify `frontend/src/features/revisions/RevisionPanel.tsx` — lineage timeline and branch-from-history behavior.
- Create `frontend/src/features/exports/ExportPanel.tsx` — explicit immutable export flow.
- Create `frontend/src/features/system/SystemStatus.tsx` — backend/storage/database/GPU/provider health.
- Modify `frontend/src/features/viewer/ViewerGrid.tsx` — DWI canonical labeling and overlay-safety rules.
- Modify `frontend/src/cornerstone/segmentation.ts` — prevent overlay on non-matching geometry.
- Modify `frontend/src/App.tsx` — coherent workflow panel composition.
- Modify `frontend/src/styles.css` — states, timeline, dialogs, workflow layout.

### Tests, CI, docs, release

- Add backend tests named in the tasks below.
- Add frontend tests named in the tasks below.
- Modify `scripts/smoke.sh` — full deterministic demo path through export.
- Create `scripts/validate_gpu.sh` — DeepISLES integration validation.
- Modify `Makefile` — `migrate`, `smoke`, `validate-gpu`, verification targets.
- Modify `.github/workflows/ci.yml` — migration/provenance/docker checks without GPU weights.
- Create `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, `SECURITY.md`, `AI_USAGE.md`.
- Update `README.md`, `docs/architecture.md`, `docs/demo.md`; add `docs/gpu.md`, `docs/workflow.md`, `docs/provenance.md`, `docs/troubleshooting.md`.

---

### Task 1: Introduce Alembic and the v1 Persistence Model

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_v1_schema.py`
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_migrations.py`
- Test fixture: `backend/tests/fixtures/mvp_schema.sql`

**Interfaces:**
- Produces ORM classes: `Case`, `SourceArtifact`, `InferenceJob`, `SegmentationArtifact`, `AnnotationRevision`, `ExportArtifact`.
- Produces `run_migrations(database_url: str) -> None` in `app.db.session`.
- All later backend tasks consume these entities.

- [ ] **Step 1: Add a representative current-MVP database fixture**

Create `backend/tests/fixtures/mvp_schema.sql` with the current four tables and insert one case, three modalities, one completed inference row, and one revision. Use fixed UUID strings so migration assertions are deterministic.

- [ ] **Step 2: Write the failing migration test**

```python
# backend/tests/test_migrations.py
from sqlalchemy import create_engine, inspect, text
from app.db.session import run_migrations


def test_mvp_database_migrates_without_losing_case(tmp_path):
    db = tmp_path / "mvp.db"
    # helper executes fixtures/mvp_schema.sql into db
    seed_mvp_database(db)

    run_migrations(f"sqlite:///{db}")

    engine = create_engine(f"sqlite:///{db}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "cases", "source_artifacts", "inference_jobs",
        "segmentation_artifacts", "annotation_revisions", "exports",
    } <= tables
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from cases")).scalar_one() == 1
        assert conn.execute(text("select count(*) from source_artifacts")).scalar_one() == 3
```

- [ ] **Step 3: Run the focused test and confirm it fails because migration infrastructure does not exist**

Run:
```bash
cd backend
pytest tests/test_migrations.py -v
```
Expected: import/configuration failure for Alembic or `run_migrations`.

- [ ] **Step 4: Add Alembic and define the v1 models**

Add dependencies in `backend/pyproject.toml`:

```toml
alembic = ">=1.13,<2"
httpx = ">=0.27,<1"
jsonschema = ">=4.23,<5"
```

Use explicit string lengths and nullable fields. Required relationships:

```python
class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str]
    name: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    __table_args__ = (UniqueConstraint("case_id", "modality"),)
    # id, case_id, modality, original_filename, relative_path, sha256,
    # file_size, shape_x/y/z, spacing_x/y/z, affine_json, datatype, created_at

class InferenceJob(Base):
    __tablename__ = "inference_jobs"
    # provider/model/service/status/timestamps/error/failure/provenance

class SegmentationArtifact(Base):
    __tablename__ = "segmentation_artifacts"
    # case_id, inference_job_id UNIQUE, path/hash/geometry/datatype

class AnnotationRevision(Base):
    __tablename__ = "annotation_revisions"
    # parent_revision_id nullable self-FK, source_segmentation_id FK,
    # path/hash/note/edit_stats_json/created_at

class ExportArtifact(Base):
    __tablename__ = "exports"
    # case_id, revision_id, mask_path, provenance_path, mask_sha256, created_at
```

- [ ] **Step 5: Implement the migration preserving current MVP data**

`0001_v1_schema.py` must:
1. rename/copy `modalities` rows into `source_artifacts`;
2. copy each completed `inference_runs` row into `inference_jobs` and create its paired `segmentation_artifacts` row;
3. migrate `annotation_revisions.source_inference_id` to `source_segmentation_id` by looking up the paired segmentation;
4. preserve IDs and paths where possible;
5. create `exports` empty;
6. set missing hashes/metadata to safe nullable migration values only for legacy rows, then let a later backfill command calculate them before export is allowed.

- [ ] **Step 6: Implement migration startup helper**

```python
def run_migrations(database_url: str) -> None:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
```

Call it before creating the FastAPI app's database session factory. Do not use `Base.metadata.create_all()` as the normal upgrade path after this task.

- [ ] **Step 7: Run migration and existing backend tests**

```bash
cd backend
pytest tests/test_migrations.py -v
pytest -v
ruff check app tests
```
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/alembic.ini backend/alembic backend/app/db backend/pyproject.toml backend/tests/test_migrations.py backend/tests/fixtures/mvp_schema.sql
git commit -m "feat: add versioned v1 database schema"
```

---

### Task 2: Add Immutable Artifacts, Checksums, NIfTI Validation, and Atomic Case Import

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
- Test: `backend/tests/test_artifacts.py`
- Test: `backend/tests/test_case_import.py`

**Interfaces:**
- Produces `sha256_file(path: Path) -> str`.
- Produces `NiftiMetadata` dataclass and `validate_source_nifti(path: Path) -> NiftiMetadata`.
- Produces `same_geometry(a: NiftiMetadata, b: NiftiMetadata, *, atol: float = 1e-5) -> bool`.
- Produces `import_case_triad(session, storage, name, uploads) -> Case`.

- [ ] **Step 1: Write checksum and validation tests**

```python
def test_sha256_file_is_stable(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"neuroannotate")
    assert sha256_file(p) == "a fixed expected digest calculated in the test fixture"


def test_source_validation_accepts_different_flair_geometry(tmp_path):
    dwi = write_test_nifti(tmp_path / "dwi.nii.gz", shape=(16,16,8), spacing=(1,1,2))
    flair = write_test_nifti(tmp_path / "flair.nii.gz", shape=(20,20,10), spacing=(1.2,1.2,3))
    assert validate_source_nifti(dwi).shape == (16,16,8)
    assert validate_source_nifti(flair).shape == (20,20,10)
```

Use an actual hard-coded SHA-256 produced once from `hashlib.sha256(b"neuroannotate").hexdigest()` in the test, not prose.

- [ ] **Step 2: Run focused tests and observe failure**

```bash
cd backend
pytest tests/test_artifacts.py -v
```

- [ ] **Step 3: Implement streaming checksum, metadata, and geometry helpers**

`NiftiMetadata` fields:

```python
@dataclass(frozen=True)
class NiftiMetadata:
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    affine: list[list[float]]
    datatype: str
    file_size: int
```

Validation rejects unreadable files, non-3D arrays, zero dimensions, non-finite affine values, and non-numeric dtypes with `ApiError(422, ...)`.

- [ ] **Step 4: Write the failing atomic triad-import API test**

```python
def test_create_case_is_atomic_when_flair_is_invalid(client, sample_nifti_bytes):
    response = client.post(
        "/api/cases",
        data={"name": "Case A"},
        files={
            "dwi": ("dwi.nii.gz", sample_nifti_bytes, "application/gzip"),
            "adc": ("adc.nii.gz", sample_nifti_bytes, "application/gzip"),
            "flair": ("flair.nii.gz", b"not-nifti", "application/gzip"),
        },
    )
    assert response.status_code == 422
    assert client.get("/api/cases").json() == []
```

- [ ] **Step 5: Run the import test and confirm it fails against the old API**

```bash
pytest tests/test_case_import.py -v
```

- [ ] **Step 6: Implement staging + atomic case import**

Create a staging directory under `data/.staging/<uuid>/`. Save all three uploads there, validate, checksum, then create `data/cases/<case_id>/source/` and use `os.replace()` for each final file. Commit `Case` + three `SourceArtifact` rows in one transaction. On any exception, roll back the DB transaction and recursively delete staging/final case directory if the case has not committed.

Final names are exactly:

```text
source/dwi.nii.gz
source/adc.nii.gz
source/flair.nii.gz
```

- [ ] **Step 7: Implement multipart `POST /api/cases`**

Signature:

```python
@router.post("", response_model=CaseDetail, status_code=201)
def create_case(
    name: Annotated[str, Form(...)],
    dwi: Annotated[UploadFile, File(...)],
    adc: Annotated[UploadFile, File(...)],
    flair: Annotated[UploadFile, File(...)],
    session: Session = Depends(get_session),
) -> CaseDetail:
    ...
```

`CaseDetail` includes source metadata and `annotation_space="DWI"`.

- [ ] **Step 8: Run focused and full backend verification**

```bash
pytest tests/test_artifacts.py tests/test_case_import.py tests/test_cases.py tests/test_modalities.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/services backend/app/api/routes/cases.py backend/app/schemas/cases.py backend/app/repositories/cases.py backend/tests
git commit -m "feat: add atomic immutable case import"
```

---

### Task 3: Add Persistent Asynchronous Inference Jobs and Demo Worker

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
- Modify: `backend/app/repositories/cases.py`
- Test: `backend/tests/test_inference_jobs.py`
- Test: `backend/tests/test_job_recovery.py`

**Interfaces:**

```python
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

- [ ] **Step 1: Write failing job lifecycle tests**

```python
def test_create_job_returns_queued_and_worker_completes(client, app_worker):
    case_id = create_valid_case(client)
    r = client.post(f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"})
    assert r.status_code == 202
    job = r.json()
    assert job["status"] == "queued"

    app_worker.run_once()
    done = client.get(f"/api/inference-jobs/{job['id']}").json()
    assert done["status"] == "completed"
    assert done["segmentation_id"]
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_inference_jobs.py -v
```

- [ ] **Step 3: Implement explicit job state transitions**

Allowed transition helper:

```python
ALLOWED = {
    "queued": {"running", "failed"},
    "running": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}
```

Reject invalid transitions with an internal domain exception; routes never permit clients to set status directly.

- [ ] **Step 4: Implement one-job worker**

`InferenceWorker.run_once()`:
1. selects the oldest queued job;
2. atomically claims it as running;
3. loads DWI/ADC/FLAIR paths;
4. invokes provider;
5. validates returned mask against DWI using Task 2 helpers;
6. atomically stores `inference/<job-id>/segmentation.nii.gz`;
7. creates `SegmentationArtifact` with SHA-256;
8. records provider/runtime/config provenance;
9. marks job completed;
10. on exception, marks failed with a typed failure category and message.

- [ ] **Step 5: Add restart recovery test**

```python
def test_running_jobs_are_failed_on_startup(session):
    job = seed_job(session, status="running")
    recover_interrupted_jobs(session)
    session.refresh(job)
    assert job.status == "failed"
    assert job.failure_category == "application_interrupted"
```

- [ ] **Step 6: Start/stop worker through FastAPI lifespan**

Use one background thread with a `threading.Event` stop flag and a short idle wait. Do not add Celery/Redis. In tests, expose `run_once()` directly so timing is deterministic.

- [ ] **Step 7: Add routes**

```text
POST /api/cases/{case_id}/inference-jobs   -> 202
GET  /api/cases/{case_id}/inference-jobs
GET  /api/inference-jobs/{job_id}
POST /api/inference-jobs/{job_id}/retry    -> creates a new queued job
GET  /api/segmentations/{id}/file.nii.gz
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
git commit -m "feat: add persistent inference job worker"
```

---

### Task 4: Harden Revision Semantics and Edit Statistics

**Files:**
- Modify: `backend/app/services/revisions.py`
- Modify: `backend/app/api/routes/revisions.py`
- Modify: `backend/app/schemas/revisions.py`
- Modify: `backend/app/repositories/cases.py`
- Test: `backend/tests/test_revisions_v1.py`

**Interfaces:**
- Produces `RevisionStats` with `added_voxels`, `removed_voxels`, `changed_voxels`, `lesion_voxels`, `lesion_volume_ml`.
- Produces `compute_revision_stats(parent: np.ndarray, current: np.ndarray, voxel_volume_mm3: float) -> RevisionStats`.
- `POST /api/cases/{case_id}/revisions` consumes `source_segmentation_id`, optional `parent_revision_id`, note, shape, raw labelmap bytes.

- [ ] **Step 1: Write failing statistics and lineage tests**

```python
def test_revision_stats_are_computed_from_parent_mask():
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

- [ ] **Step 3: Enforce DWI geometry and binary mask invariant**

Update the revision writer so the reference is always the case DWI source artifact, not whichever file is convenient. Validate shape and affine with `same_geometry`; binarize incoming browser labelmap to `uint8` before saving; reject any inability to reconstruct DWI geometry.

- [ ] **Step 4: Add immutable parent/source lineage**

For a first human revision based on AI mask: `parent_revision_id=None`, `source_segmentation_id=<ai mask>`.
For later revisions: `parent_revision_id=<selected revision>`, `source_segmentation_id` remains the originating AI segmentation.

- [ ] **Step 5: Persist SHA-256 and stats JSON**

Write mask to a temporary path, validate it, compute SHA-256 and stats, atomically rename, then create the DB row. If DB commit fails, remove the new file.

- [ ] **Step 6: Verify**

```bash
pytest tests/test_revisions.py tests/test_revisions_v1.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/revisions.py backend/app/api/routes/revisions.py backend/app/schemas/revisions.py backend/app/repositories/cases.py backend/tests/test_revisions_v1.py
git commit -m "feat: add immutable revision lineage and statistics"
```

---

### Task 5: Add Provenance-Rich Immutable Exports

**Files:**
- Create: `backend/app/services/provenance.py`
- Create: `backend/app/services/exports.py`
- Create: `backend/app/schemas/exports.py`
- Modify: `backend/app/api/routes/exports.py`
- Modify: `backend/app/repositories/cases.py`
- Test: `backend/tests/test_provenance.py`
- Test: `backend/tests/test_exports_v1.py`
- Create: `backend/tests/fixtures/provenance_schema_v1.json`

**Interfaces:**
- Produces `build_provenance(case, sources, job, segmentation, revision, export, software) -> dict[str, object]`.
- Produces `create_export(session, storage, case_id: str, revision_id: str) -> ExportArtifact`.

- [ ] **Step 1: Write failing provenance privacy/schema test**

```python
def test_provenance_has_required_sections_and_no_local_paths(provenance):
    assert provenance["schema"] == "neuroannotate.provenance"
    assert provenance["schema_version"] == "1.0"
    assert provenance["case"]["annotation_space"] == "DWI"
    assert set(provenance["sources"]) == {"DWI", "ADC", "FLAIR"}
    rendered = json.dumps(provenance)
    assert "/home/" not in rendered
    assert "original_filename" not in rendered
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_provenance.py tests/test_exports_v1.py -v
```

- [ ] **Step 3: Implement deterministic provenance builder**

Required top-level sections exactly:

```python
{
    "schema": "neuroannotate.provenance",
    "schema_version": "1.0",
    "software": {...},
    "export": {...},
    "case": {...},
    "sources": {"DWI": {...}, "ADC": {...}, "FLAIR": {...}},
    "ai_segmentation": {...},
    "annotation": {...},
    "output": {...},
    "disclaimer": "Research software only. Not for diagnosis or clinical decision-making.",
}
```

Sort JSON keys and indent with 2 spaces when writing the file so identical metadata produces stable bytes.

- [ ] **Step 4: Implement export snapshot creation**

Copy the selected immutable revision bytes to `exports/<export-id>/lesion-mask.nii.gz`, calculate its SHA-256, build provenance, validate JSON against `provenance_schema_v1.json`, write `provenance.json` through a temp file, then commit `ExportArtifact`.

- [ ] **Step 5: Implement routes**

```text
POST /api/cases/{case_id}/exports      body {"revision_id":"..."}
GET  /api/exports/{id}/mask
GET  /api/exports/{id}/provenance
GET  /api/exports/{id}/bundle
```

Bundle entries must be exactly `lesion-mask.nii.gz` and `provenance.json`.

- [ ] **Step 6: Verify byte/hash consistency**

Add a test that downloads the mask, recomputes SHA-256, and asserts it equals both `ExportArtifact.mask_sha256` and `provenance["output"]["sha256"]`.

- [ ] **Step 7: Verify**

```bash
pytest tests/test_provenance.py tests/test_exports_v1.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/provenance.py backend/app/services/exports.py backend/app/schemas/exports.py backend/app/api/routes/exports.py backend/app/repositories/cases.py backend/tests
git commit -m "feat: add reproducible annotation exports"
```

---

### Task 6: Update Frontend API, Types, and Workspace State for v1 Resources

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/state/workspace.ts`
- Test: `frontend/tests/apiUrls.test.ts`
- Create: `frontend/tests/workspace.test.ts`

**Interfaces:**

```ts
export type InferenceStatus = 'queued' | 'running' | 'completed' | 'failed';
export interface CaseDetail { id: string; name: string; annotation_space: 'DWI'; sources: SourceArtifact[]; }
export interface InferenceJob { id: string; case_id: string; provider: string; status: InferenceStatus; segmentation_id?: string | null; ... }
export interface Revision { id: string; parent_revision_id: string | null; source_segmentation_id: string; edit_stats: RevisionStats; ... }
export interface ExportArtifact { id: string; revision_id: string; mask_sha256: string; mask_url: string; provenance_url: string; bundle_url: string; }
```

- [ ] **Step 1: Write failing API URL and workspace dirty-state tests**

```ts
it('uses the v1 segmentation-by-id URL', () => {
  expect(segmentationFileUrl('seg-1')).toContain('/api/segmentations/seg-1/file.nii.gz');
});

it('does not clear dirty state until save succeeds', () => {
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

- [ ] **Step 3: Implement atomic case import client**

```ts
export async function createCase(input: {
  name: string;
  dwi: File;
  adc: File;
  flair: File;
}): Promise<CaseDetail> {
  const form = new FormData();
  form.set('name', input.name);
  form.set('dwi', input.dwi);
  form.set('adc', input.adc);
  form.set('flair', input.flair);
  return request('/api/cases', { method: 'POST', body: form });
}
```

- [ ] **Step 4: Implement job/revision/export clients and URLs**

Add typed functions for create/list/get/retry jobs, list/save revisions, create/get export, provider status, and system health. Keep `.nii.gz` suffixes on all Cornerstone-served NIfTI URLs.

- [ ] **Step 5: Expand workspace store**

Store: `selectedCaseId`, `selectedModality`, `loadedSegmentationId`, `loadedRevisionId`, `baseRevisionId`, `dirty`, `activeJobId`, and actions for loading/saving/discarding state. Do not put large voxel arrays in Zustand.

- [ ] **Step 6: Verify**

```bash
npm test -- --run tests/apiUrls.test.ts tests/workspace.test.ts
npm run lint
npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/client.ts frontend/src/state/workspace.ts frontend/tests
git commit -m "feat: add v1 frontend resource clients"
```

---

### Task 7: Build the v1 Case, Inference, Annotation, Revision, Export, and Status Workflow UI

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
- Test: `frontend/tests/CaseUploadPanel.test.tsx`
- Modify: `frontend/tests/InferenceControls.test.tsx`
- Modify: `frontend/tests/RevisionPanel.test.tsx`
- Create: `frontend/tests/ExportPanel.test.tsx`
- Create: `frontend/tests/SystemStatus.test.tsx`

**Interfaces:**
- Uses Task 6 API functions and store actions only.
- `InferenceControls` receives/loads provider info and active job status; it does not invoke Cornerstone directly.
- `ExportPanel` requires a saved revision and `dirty === false`.

- [ ] **Step 1: Write failing atomic case form test**

Test that Create Case is disabled until name + all three files are selected, and one submit calls `createCase({name,dwi,adc,flair})` exactly once.

- [ ] **Step 2: Write failing inference-state tests**

Cover visible copy and buttons for `queued`, `running`, `completed`, and `failed`; Retry is shown only on failed jobs. Demo provider must visibly say it is a deterministic demonstration and not a trained medical model.

- [ ] **Step 3: Write failing export dirty-state test**

```ts
it('blocks export while annotation changes are unsaved', () => {
  render(<ExportPanel revision={revision} dirty={true} />);
  expect(screen.getByRole('button', { name: /create export/i })).toBeDisabled();
  expect(screen.getByText(/save your annotation changes/i)).toBeInTheDocument();
});
```

- [ ] **Step 4: Run focused UI tests and confirm failures**

```bash
cd frontend
npm test -- --run tests/CaseUploadPanel.test.tsx tests/InferenceControls.test.tsx tests/RevisionPanel.test.tsx tests/ExportPanel.test.tsx tests/SystemStatus.test.tsx
```

- [ ] **Step 5: Implement the new case flow**

Show each selected source with filename locally, and once the server returns the case show dimensions/spacing/datatype from server metadata. Surface geometry mismatch as informational text only. Case list empty state: `No MRI cases yet` + `Create a case using DWI, ADC, and FLAIR NIfTI volumes.`

- [ ] **Step 6: Implement inference polling**

When a job is queued/running, poll `GET /api/inference-jobs/{id}` every 2000 ms while the case remains selected. Stop polling on completed/failed/unmount. Never open a long-running browser request to the model service.

- [ ] **Step 7: Implement annotation/revision workflow**

Show current base, opacity, Brush/Erase, brush size, Undo/Redo, unsaved-change count, note field, Save Revision. On failed save, leave `dirty=true`; clear it only after the backend returns the new revision.

- [ ] **Step 8: Implement revision timeline**

Render AI segmentation as timeline root, immutable revisions in creation order, `Current` marker, note, timestamp, added/removed counts, and `Based on: Revision X` when an older revision is selected for editing.

- [ ] **Step 9: Implement export and system status panels**

Export panel: selected revision, DWI native space, SHA-256, Create Export, Download Bundle, Download Mask, View Provenance. System status: backend/storage/database and GPU/provider mode. GPU absence in demo mode is neutral, not an error.

- [ ] **Step 10: Compose the workflow in `App.tsx` and style it**

Keep the existing three-area layout: cases | viewer | workflow. Preserve the existing Cornerstone viewer mounting path and current runtime fixes.

- [ ] **Step 11: Verify**

```bash
npm test -- --run
npm run lint
npm run build
```

- [ ] **Step 12: Commit**

```bash
git add frontend/src frontend/tests
git commit -m "feat: build v1 annotation workflow UI"
```

---

### Task 8: Enforce DWI-Canonical Overlay Safety in Cornerstone

**Files:**
- Modify: `frontend/src/features/viewer/ViewerGrid.tsx`
- Modify: `frontend/src/cornerstone/segmentation.ts`
- Modify: `frontend/src/cornerstone/viewer.ts`
- Test: `frontend/tests/ViewerGrid.test.tsx`
- Create: `frontend/tests/overlayGeometry.test.ts`

**Interfaces:**
- Produces `canDisplaySegmentationOn(source: VolumeGeometry, dwi: VolumeGeometry): boolean`.
- DWI always supports DWI-space lesion overlay; ADC/FLAIR only when shape + affine match within frontend tolerance derived from backend metadata.

- [ ] **Step 1: Write failing geometry policy tests**

```ts
it('allows DWI overlay and blocks mismatched FLAIR overlay', () => {
  expect(canDisplaySegmentationOn(dwi, dwi)).toBe(true);
  expect(canDisplaySegmentationOn(flairDifferentGeometry, dwi)).toBe(false);
});
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd frontend
npm test -- --run tests/overlayGeometry.test.ts tests/ViewerGrid.test.tsx
```

- [ ] **Step 3: Implement overlay guard before attaching segmentation representation**

If selected modality is mismatched, remove/hide the segmentation representation and render: `Segmentation overlay unavailable in this geometry.` Never resample in the browser for v1.0.

- [ ] **Step 4: Preserve viewer runtime regressions tests**

Run existing `volumeLoading.test.ts` and URL suffix tests in the same verification command.

- [ ] **Step 5: Verify**

```bash
npm test -- --run tests/overlayGeometry.test.ts tests/ViewerGrid.test.tsx tests/volumeLoading.test.ts tests/apiUrls.test.ts
npm test -- --run
npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/viewer/ViewerGrid.tsx frontend/src/cornerstone frontend/tests
git commit -m "feat: enforce DWI-space overlay safety"
```

---

### Task 9: Add the DeepISLES HTTP Inference Service and Backend Provider

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
- Test: `backend/tests/test_deepisles_provider.py`

**Interfaces:**

DeepISLES service:

```text
GET  /health
GET  /v1/info
POST /v1/segment  multipart fields: dwi, adc, flair
```

`/v1/info` response:

```json
{
  "service": "neuroannotate-deepisles",
  "service_version": "1.0.0",
  "engine": "DeepISLES",
  "upstream_commit": "7658b608fc0d890cf14448ff3e58c47ad5c761e7",
  "weights_record": "14026715",
  "device": "cuda",
  "cuda_available": true,
  "configuration": {
    "skull_strip": false,
    "fast": false,
    "save_team_outputs": false,
    "results_mni": false,
    "parallelize": true
  }
}
```

- [ ] **Step 1: Write mock service contract tests without loading model weights**

Monkeypatch `runner.segment(...)` to return a tiny temporary NIfTI. Assert `/v1/segment` accepts three multipart files and returns a gzip NIfTI response plus identifying metadata headers or a JSON metadata envelope with a binary endpoint chosen consistently in the implementation.

Use the simpler contract: return a ZIP containing exactly `segmentation.nii.gz` and `metadata.json`; the backend provider unpacks it. This avoids trying to mix JSON and raw NIfTI in one HTTP body.

- [ ] **Step 2: Run contract tests and confirm failure**

```bash
pytest inference-service/tests/test_api_contract.py -v
```

- [ ] **Step 3: Implement pinned upstream build**

`inference-service/Dockerfile` clones exactly:

```dockerfile
ARG DEEPISLES_COMMIT=7658b608fc0d890cf14448ff3e58c47ad5c761e7
RUN git clone https://github.com/ezequieldlrosa/DeepIsles.git /opt/deepisles \
 && cd /opt/deepisles \
 && git checkout "$DEEPISLES_COMMIT"
```

Match upstream's Python 3.8 / PyTorch 1.11 / CUDA 11.3 environment rather than upgrading model dependencies opportunistically. Add only FastAPI/Uvicorn wrapper dependencies after upstream installs.

- [ ] **Step 4: Implement reproducible weight fetch script**

`fetch_weights.sh`:

```bash
set -euo pipefail
url='https://zenodo.org/records/14026715/files/stroke_ensemble_weights.7z?download=1'
expected_md5='be5b6dfcd66b55c2e6dc6db9a5880f7f'
curl -fL "$url" -o /models/weights.7z
echo "$expected_md5  /models/weights.7z" | md5sum -c -
7z x /models/weights.7z -o/opt/deepisles -y
```

Weights live in a Docker volume/cache, not Git.

- [ ] **Step 5: Implement runner using upstream ensemble**

```python
from src.isles22_ensemble import IslesEnsemble

ensemble = IslesEnsemble()
ensemble.predict_ensemble(
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
```

After inference, locate the final ensemble lesion NIfTI from the upstream result directory, validate it is readable, and copy it to the service response staging directory as `segmentation.nii.gz`.

- [ ] **Step 6: Implement backend `DeepISLESProvider` against the ZIP contract**

Use `httpx.Client(timeout=None)` from the background worker only. POST three source files, require 2xx, unpack into a temporary directory, parse `metadata.json`, and return `ProviderResult`. Provider unavailability maps to `provider_unavailable`; non-2xx/model execution maps to `provider_runtime_failure`.

- [ ] **Step 7: Verify mock contract**

```bash
cd backend
pytest tests/test_deepisles_provider.py -v
cd ..
pytest inference-service/tests/test_api_contract.py -v
```

- [ ] **Step 8: Commit**

```bash
git add inference-service backend/app/services/inference/deepisles.py backend/app/services/inference/registry.py backend/tests/test_deepisles_provider.py
git commit -m "feat: add DeepISLES inference service contract"
```

---

### Task 10: Add Docker GPU Profile, Health Checks, and GPU Validation Command

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `Makefile`
- Create: `scripts/validate_gpu.sh`
- Modify: `backend/app/api/routes/health.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Compose service name: `deepisles`.
- Backend environment: `NEUROANNOTATE_DEEPISLES_URL=http://deepisles:8080`.
- GPU profile: `profiles: ["gpu"]`.

- [ ] **Step 1: Write failing health/provider-status test**

Health response must separate core app health from optional provider health:

```json
{
  "status": "ok",
  "database": "ok",
  "storage": "ok",
  "inference": {
    "mode": "demo",
    "deepisles": "not_enabled"
  }
}
```

GPU service being disabled must not make `/api/health` fail in default mode.

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_health.py -v
```

- [ ] **Step 3: Add Compose GPU profile**

Keep existing backend/frontend unchanged in default profile. Add `deepisles` only under `gpu`, private network connectivity, NVIDIA reservation/device access, model-cache volume, and a healthcheck calling `http://localhost:8080/health`.

- [ ] **Step 4: Add `scripts/validate_gpu.sh`**

The script must:
1. require `nvidia-smi` and Docker;
2. run `docker compose --profile gpu up -d --build`;
3. wait for DeepISLES health;
4. verify `/v1/info` identifies the pinned commit;
5. import a documented real test case from a user-provided directory via `NEUROANNOTATE_GPU_TEST_CASE`; do not redistribute patient data;
6. trigger a DeepISLES job;
7. poll until completed/failed with a 30-minute timeout;
8. download the segmentation and provenance export;
9. use a Python one-liner/NiBabel to assert binary mask + DWI geometry;
10. print PASS only after all checks succeed.

- [ ] **Step 5: Add Make targets**

```make
migrate:
	cd backend && alembic upgrade head

validate-gpu:
	./scripts/validate_gpu.sh
```

- [ ] **Step 6: Verify default Compose remains GPU-free**

```bash
docker compose config
docker compose config --profiles
docker compose --profile gpu config
```

Expected: default config does not require NVIDIA/DeepISLES; `gpu` profile includes it.

- [ ] **Step 7: Verify backend**

```bash
cd backend
pytest tests/test_health.py -v
pytest -v
ruff check app tests
```

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml .env.example Makefile scripts/validate_gpu.sh backend/app/api/routes/health.py backend/tests/test_health.py
git commit -m "feat: add optional DeepISLES GPU deployment"
```

---

### Task 11: Add Deterministic End-to-End Demo Fixture and Expand CI

**Files:**
- Modify: `backend/app/scripts/generate_demo_data.py`
- Modify: `backend/app/scripts/seed_demo_case.py`
- Create: `backend/tests/test_v1_workflow.py`
- Modify: `scripts/smoke.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `Makefile`

**Interfaces:**
- Demo generator produces deterministic DWI, ADC, FLAIR and expected demo mask from a fixed seed.
- Smoke path exercises HTTP APIs through export, not private service functions.

- [ ] **Step 1: Write failing full backend workflow test**

```python
def test_full_demo_workflow(client):
    case = create_case_from_generated_triad(client)
    job = client.post(f"/api/cases/{case['id']}/inference-jobs", json={"provider":"demo"}).json()
    run_worker_until_terminal(job["id"])
    completed = client.get(f"/api/inference-jobs/{job['id']}").json()
    revision = save_noop_revision_from_segmentation(client, case, completed)
    export = client.post(f"/api/cases/{case['id']}/exports", json={"revision_id": revision["id"]}).json()
    assert client.get(export["bundle_url"]).status_code == 200
```

- [ ] **Step 2: Run and confirm any missing integration behavior**

```bash
cd backend
pytest tests/test_v1_workflow.py -v
```

- [ ] **Step 3: Make demo data deterministic and non-patient**

Use a fixed NumPy RNG seed and synthetic ellipsoids/intensity fields. Record expected shape/spacing and demo-mask checksum in the test, generated from the deterministic algorithm.

- [ ] **Step 4: Expand `scripts/smoke.sh`**

Smoke must perform: health -> create triad case -> start demo job -> poll -> get segmentation -> save revision -> create export -> download bundle -> inspect ZIP names. Fail on any non-2xx or terminal failed job.

- [ ] **Step 5: Expand CI**

Backend job adds:

```yaml
- run: alembic upgrade head
- run: pytest -v
```

Add a separate `docker-config` job:

```yaml
- run: docker compose config >/dev/null
- run: docker compose --profile gpu config >/dev/null
```

Do not build/run the heavy DeepISLES image in hosted CI.

- [ ] **Step 6: Add `make verify`**

```make
verify:
	cd backend && ruff check app tests && pytest -q
	cd frontend && npm run lint && npm test -- --run && npm run build
	docker compose config >/dev/null
	docker compose --profile gpu config >/dev/null
```

- [ ] **Step 7: Run full local verification**

```bash
make verify
```
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add backend/app/scripts backend/tests/test_v1_workflow.py scripts/smoke.sh .github/workflows/ci.yml Makefile
git commit -m "test: cover complete v1 demo workflow"
```

---

### Task 12: Complete Research-Software Documentation and Release Metadata

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
- Test: `backend/tests/test_docs_metadata.py`

**Interfaces:**
- Documentation must describe exactly the commands implemented by earlier tasks.
- Citation metadata version: `1.0.0`.

- [ ] **Step 1: Write failing metadata test**

```python
def test_release_metadata_files_exist(repo_root):
    required = [
        "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
        "CITATION.cff", "SECURITY.md", "AI_USAGE.md",
        "docs/gpu.md", "docs/workflow.md", "docs/provenance.md",
        "docs/troubleshooting.md",
    ]
    for path in required:
        assert (repo_root / path).is_file(), path
```

Also parse `CITATION.cff` and assert `version: 1.0.0`, repository URL, and project title.

- [ ] **Step 2: Run and confirm failure**

```bash
cd backend
pytest tests/test_docs_metadata.py -v
```

- [ ] **Step 3: Rewrite README around v1 workflow**

README sections, in order:
1. one-paragraph product description;
2. research-use disclaimer;
3. screenshot/demo placeholder reference only if an actual screenshot asset exists;
4. Quick Start — `docker compose up`;
5. GPU Quick Start — link to `docs/gpu.md`;
6. core workflow;
7. architecture diagram;
8. testing/contributing;
9. citation;
10. license/third-party attribution.

Remove wording that presents nnU-Net as the planned default real provider; DeepISLES is the v1 provider.

- [ ] **Step 4: Document DeepISLES installation exactly**

`docs/gpu.md` includes NVIDIA Container Toolkit prerequisite, weight size (~9.1 GB), Zenodo record/file/MD5, model-cache location, `docker compose --profile gpu up`, `make validate-gpu`, and troubleshooting for unavailable GPU/service/weights.

- [ ] **Step 5: Document provenance and privacy**

`docs/provenance.md` documents every JSON section, DWI canonical space, SHA-256 meaning, omission of host paths/original filenames, and that edit statistics are descriptive rather than clinical metrics.

- [ ] **Step 6: Add AI usage disclosure log**

`AI_USAGE.md` states that generative AI assisted architecture planning, implementation planning, code/documentation work where applicable, and that maintainers review, test, and remain responsible for accepted changes. Keep it factual and update it during implementation rather than retroactively inventing details.

- [ ] **Step 7: Verify metadata and all suites**

```bash
cd backend && pytest tests/test_docs_metadata.py -v && pytest -q && ruff check app tests
cd ../frontend && npm run lint && npm test -- --run && npm run build
cd .. && docker compose config >/dev/null && docker compose --profile gpu config >/dev/null
```

- [ ] **Step 8: Commit**

```bash
git add README.md CHANGELOG.md CONTRIBUTING.md CODE_OF_CONDUCT.md CITATION.cff SECURITY.md AI_USAGE.md docs backend/tests/test_docs_metadata.py
git commit -m "docs: prepare NeuroAnnotate v1 research software release"
```

---

### Task 13: Final v1 Verification, Migration Drill, and Release Candidate Gate

**Files:**
- Modify only if verification reveals a defect; fixes must include a regression test in the owning task's test area.
- Verify: entire repository.

**Interfaces:**
- This task produces no new feature API. It is the evidence gate for the release candidate.

- [ ] **Step 1: Start from a clean worktree state**

```bash
git status --short
```
Expected: empty output before verification.

- [ ] **Step 2: Run backend quality gates**

```bash
cd backend
ruff check app tests
pytest -v
alembic upgrade head
alembic current
```
Expected: zero lint/test failures; Alembic at head.

- [ ] **Step 3: Run frontend quality gates**

```bash
cd ../frontend
npm run lint
npm test -- --run
npm run build
```
Expected: zero failures and successful production build.

- [ ] **Step 4: Run Compose validation and deterministic smoke**

```bash
cd ..
docker compose config >/dev/null
docker compose --profile gpu config >/dev/null
docker compose up -d --build
./scripts/smoke.sh
docker compose down
```
Expected: smoke script reaches export and reports PASS.

- [ ] **Step 5: Perform a real migration drill on a copy of an MVP database**

Copy a representative pre-v1 `neuroannotate.db` to a temporary directory, point the backend at the copy, run migrations, start the API, and verify the old case, modalities, completed inference, and revision are still listable. Never test destructive migration behavior against the user's primary local database.

- [ ] **Step 6: Run GPU validation on a supported NVIDIA host when available**

```bash
NEUROANNOTATE_GPU_TEST_CASE=/absolute/path/to/licensed/test-case make validate-gpu
```
Expected: service health, actual DeepISLES job, DWI-space binary mask, provenance, and export round-trip all pass. If no supported NVIDIA host/test case is available, record GPU validation as a release blocker rather than claiming v1.0 GPU readiness.

- [ ] **Step 7: Inspect repository diff/history for accidental data or weights**

```bash
git status --short
git ls-files | grep -Ei '\.(nii|nii\.gz|7z|pt|pth|ckpt)$' || true
git log --oneline --decorate -15
```
Expected: no patient MRI or DeepISLES weights tracked; only intentional synthetic fixtures if they are explicitly approved and small.

- [ ] **Step 8: Create release-candidate commit only if fixes were required**

If Step 1-7 required changes, run the complete relevant verification again before committing. If no changes were required, do not create an empty commit.

- [ ] **Step 9: Open the implementation PR and wait for CI**

PR body must summarize:
- atomic triad import;
- migration strategy;
- async jobs;
- revision/provenance/export model;
- frontend workflow;
- optional DeepISLES GPU service;
- verification commands run;
- explicit note that the software is for research use only.

Do not merge until GitHub Actions is green and review findings are resolved.

---

## Plan Self-Review Results

### Spec coverage

- Architecture/deployment modes: Tasks 3, 9, 10.
- Atomic immutable source triads + SHA-256: Task 2.
- DWI canonical annotation geometry: Tasks 2, 4, 8, 9.
- Persistent async jobs, one GPU job, restart recovery, no auto-retry: Task 3 and Task 10.
- DeepISLES real provider, pinned upstream source, external weights: Task 9 and Task 10.
- Immutable complete revisions + lineage + statistics: Task 4.
- NIfTI + provenance JSON + ZIP export: Task 5.
- Workflow UI/empty states/status: Tasks 6-8.
- Alembic preservation of existing data: Task 1 and Task 13.
- Deterministic CPU CI + explicit GPU validation: Tasks 11 and 13.
- JOSS/research-software metadata and AI disclosure: Task 12.
- No DICOM/auth/cloud/collaboration/advanced 3D editing introduced: enforced by Global Constraints and no task adds them.

### Type/interface consistency

- Job statuses are consistently `queued | running | completed | failed`.
- DWI-space segmentation is referenced by `SegmentationArtifact.id` and revision lineage by `AnnotationRevision.id`.
- Export always points to a saved revision and never serializes unsaved browser state.
- Frontend file URLs retain `.nii.gz` suffixes needed by Cornerstone.
- DeepISLES provider and demo provider both return the same `ProviderResult` shape.

### Scope

This is a large but single integrated release plan because every major subsystem is coupled by the same artifact/job/revision/export workflow and each task leaves the application independently testable. The tasks are intentionally ordered so the deterministic CPU path is fully functional before the GPU integration is introduced.
