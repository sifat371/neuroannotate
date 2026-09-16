# NeuroAnnotate v1.0 Design Specification

**Date:** 2026-09-17  
**Status:** Approved design, pending implementation plan  
**Project:** NeuroAnnotate  
**Repository:** `sifat371/neuroannotate`

## 1. Purpose

NeuroAnnotate v1.0 will be a self-hosted, open-source MRI annotation workspace for ischemic stroke research. Its primary workflow is:

1. import DWI, ADC, and FLAIR NIfTI volumes;
2. review the source MRI volumes in a multiplanar viewer;
3. generate an AI-assisted lesion segmentation using either a deterministic demo provider or a real DeepISLES GPU service;
4. manually correct the lesion mask with simple 2D annotation tools;
5. save complete, immutable annotation revisions;
6. export a standard NIfTI lesion mask together with a provenance JSON sidecar.

The product is research software only. It is not a medical device and must not be presented as suitable for diagnosis or clinical decision-making.

The v1.0 goal is a bounded, reproducible research-software release, not a general-purpose radiology platform.

## 2. Product Positioning and Scope

### 2.1 Target

NeuroAnnotate v1.0 is designed as:

- open-source research software;
- self-hosted and local-first;
- single-user in v1.0;
- NIfTI-only;
- focused on ischemic stroke lesion annotation;
- architected to be JOSS-ready, while recognizing that actual JOSS submission eligibility and policy requirements must be re-checked at submission time.

### 2.2 Required modalities

The real-model workflow requires:

- DWI;
- ADC;
- FLAIR.

All three inputs must be readable 3D NIfTI files. They do not need to share identical voxel geometry.

### 2.3 Explicit non-goals for v1.0

The following are out of scope:

- DICOM or PACS integration;
- authentication or RBAC;
- multi-user collaboration;
- hosted cloud deployment;
- automatic slice interpolation;
- advanced 3D sculpting/editing;
- active learning;
- uncertainty estimation;
- clinical decision support;
- a Redis/Celery queue;
- a custom proprietary export format.

## 3. System Architecture

NeuroAnnotate will evolve the current working React/FastAPI application rather than being rewritten.

```text
React + Cornerstone3D
        |
        | REST
        v
FastAPI Application
        |
        |-- Case Manager
        |-- Artifact Storage
        |-- SQLite + Alembic
        |-- Annotation / Revision Service
        |-- Export / Provenance Service
        |-- Inference Job Worker
        |
        `-- SegmentationProvider interface
                 |
                 |-- DemoProvider
                 `-- DeepISLESProvider
                           |
                           | private HTTP
                           v
                  GPU Inference Service
                  NVIDIA + DeepISLES
```

### 3.1 Deployment modes

Default installation:

```bash
docker compose up
```

This starts the normal application with the deterministic demo provider and no GPU requirement.

GPU installation:

```bash
docker compose --profile gpu up
```

This additionally starts the DeepISLES inference service with NVIDIA/CUDA support.

The FastAPI application must not import or depend directly on DeepISLES, CUDA, or its training/inference environment. The real model is isolated behind an HTTP provider boundary.

## 4. Core Domain Model

The filesystem stores NIfTI and JSON artifacts. SQLite stores metadata, relationships, lifecycle state, and provenance references. MRI image bytes are never stored as database blobs.

The v1.0 domain model is:

```text
Case
 |-- DWI source artifact
 |-- ADC source artifact
 |-- FLAIR source artifact
 |
 |-- Inference Job(s)
 |     `-- Segmentation Artifact on success
 |
 |-- Annotation Revision(s)
 |
 `-- Export Snapshot(s)
```

### 4.1 Cases

A case stores only human-readable metadata and identity.

Required fields:

- `id` UUID;
- `name`;
- `created_at`;
- `updated_at`.

Human-readable case names are metadata only and must never be used as storage paths.

### 4.2 Source artifacts

A source artifact represents one immutable imported modality.

Required fields:

- `id` UUID;
- `case_id`;
- `modality` (`DWI`, `ADC`, or `FLAIR`);
- `original_filename` for local usability only;
- `relative_path`;
- `sha256`;
- `file_size`;
- shape;
- voxel spacing;
- affine;
- datatype;
- `created_at`.

Each case has at most one active source artifact for each required modality in v1.0.

### 4.3 Inference jobs

An inference job represents an attempt to generate an AI segmentation.

Required fields:

- `id` UUID;
- `case_id`;
- `provider`;
- `model_name`;
- `model_version`;
- `service_version`;
- `status`;
- `created_at`;
- `started_at`;
- `completed_at`;
- `error_message`;
- `failure_category`;
- `provenance_json`.

Allowed states:

```text
queued -> running -> completed
                 `-> failed
```

There is no automatic retry in v1.0. A retry creates a new inference job.

### 4.4 Segmentation artifacts

A segmentation artifact is created only when an inference job completes successfully and its output passes NeuroAnnotate validation.

Required fields:

- `id` UUID;
- `case_id`;
- `inference_job_id`;
- `relative_path`;
- `sha256`;
- shape;
- spacing;
- affine;
- datatype;
- `created_at`.

### 4.5 Annotation revisions

Every saved revision is a complete immutable `.nii.gz` mask.

Required fields:

- `id` UUID;
- `case_id`;
- `parent_revision_id`, nullable;
- `source_segmentation_id`;
- `relative_path`;
- `sha256`;
- `note`, optional;
- `edit_stats_json`;
- `created_at`.

A revision is independently loadable and never requires replaying edit diffs.

### 4.6 Exports

An export is an immutable snapshot tied to exactly one saved revision.

Required fields:

- `id` UUID;
- `case_id`;
- `revision_id`;
- `mask_path`;
- `provenance_path`;
- `mask_sha256`;
- `created_at`.

Editing a case after an export is created must never mutate that export.

## 5. Managed Workspace Layout

All imported source files are copied into a NeuroAnnotate-managed workspace and treated as immutable.

```text
data/
|-- neuroannotate.db
`
`-- cases/
    `-- <case-uuid>/
        |-- source/
        |   |-- dwi.nii.gz
        |   |-- adc.nii.gz
        |   `-- flair.nii.gz
        |
        |-- inference/
        |   `-- <job-uuid>/
        |       |-- segmentation.nii.gz
        |       `-- inference.json
        |
        |-- revisions/
        |   |-- <revision-uuid>.nii.gz
        |   `-- ...
        |
        `-- exports/
            `-- <export-uuid>/
                |-- lesion-mask.nii.gz
                `-- provenance.json
```

Absolute filesystem paths must never appear in portable exports.

### 5.1 Import transaction

Import follows this order:

```text
upload
  -> temporary file
  -> validate NIfTI
  -> extract metadata
  -> calculate SHA-256
  -> copy into managed case workspace
  -> atomic rename
  -> create database artifact record
```

A validation failure must leave no partial artifact record.

## 6. Canonical Annotation Space

DWI native space is the canonical annotation space.

```text
Source images:     native, immutable
Annotation space:  DWI native space
AI lesion mask:    DWI native space
Human revisions:   DWI native space
Final export:      DWI native space
```

ADC and FLAIR remain native-space reference images.

NeuroAnnotate must not reject a case merely because ADC or FLAIR geometry differs from DWI.

The viewer may synchronize navigation using physical/world coordinates where supported, but it must not show a segmentation overlay on a modality whose geometry does not safely align with the DWI-space mask.

If ADC or FLAIR exactly matches the DWI geometry, the mask overlay may be displayed there.

## 7. NIfTI Validation Rules

### 7.1 Source images

Each source modality must be:

- readable NIfTI;
- 3D;
- non-empty;
- have plausible finite dimensions;
- have a finite affine/header geometry;
- use a supported numeric datatype.

NeuroAnnotate records:

- shape;
- voxel spacing;
- affine;
- datatype;
- byte size;
- SHA-256.

### 7.2 AI masks and revisions

Every persisted editable or exported lesion mask must satisfy:

- readable NIfTI;
- 3D;
- binary values only (`0` background, `1` lesion);
- same shape as DWI;
- affine equal to DWI within an explicitly defined numerical tolerance;
- finite values;
- persisted as `uint8`.

This invariant is central to v1.0:

> Every editable or exported lesion mask is valid in the immutable DWI native space.

## 8. Inference Architecture

### 8.1 Provider boundary

The current conceptual `SegmentationProvider` abstraction remains, but real inference moves behind an HTTP service.

Expected provider implementations:

- `DemoProvider`;
- `DeepISLESProvider`.

Future providers may be added without changing the viewer, revision system, or export format.

### 8.2 DeepISLES inference service

The GPU service is deliberately narrow and effectively stateless with respect to NeuroAnnotate cases.

Required endpoints:

```text
GET  /health
GET  /v1/info
POST /v1/segment
```

`/v1/info` exposes identifying runtime metadata such as:

- service name/version;
- engine/model name;
- model version or upstream identifier;
- CUDA availability;
- device information.

`POST /v1/segment` receives DWI, ADC, and FLAIR NIfTI volumes using multipart transfer over the private Docker network and returns:

- a DWI-space lesion segmentation NIfTI;
- explicit inference metadata needed for provenance.

The DeepISLES service owns its required preprocessing. NeuroAnnotate does not duplicate or replace model-specific registration/resampling preprocessing.

### 8.3 Why HTTP rather than shared paths

The model service must not depend on NeuroAnnotate database paths or case-directory layout. HTTP transfer keeps the contract explicit and makes it possible to move the inference service to another GPU host later without redesigning the application.

## 9. Asynchronous Job Lifecycle

The browser never holds open a model inference request.

Job creation:

```text
POST /api/cases/{case_id}/inference-jobs
```

The FastAPI application:

1. verifies DWI/ADC/FLAIR exist;
2. creates a persistent `queued` job;
3. returns the job immediately;
4. lets a lightweight background worker claim the oldest queued job;
5. marks the job `running`;
6. calls the provider;
7. validates the returned mask;
8. stores the immutable segmentation artifact;
9. marks the job `completed`.

The UI polls the job status while the case is open. WebSockets are not required for v1.0.

### 9.1 Concurrency

Only one GPU inference job runs at a time in v1.0. Additional jobs remain queued.

### 9.2 Restart behavior

On backend startup:

- queued jobs remain queued;
- jobs found in `running` are changed to `failed` with a reason such as `Interrupted by application restart`;
- interrupted jobs are never silently resumed;
- the user may explicitly retry, creating a new job.

### 9.3 Failure categories

At minimum, distinguish:

- provider unavailable;
- provider runtime failure;
- invalid model output;
- input validation failure;
- application restart/interruption;
- artifact persistence failure.

A failed job does not create a segmentation artifact.

## 10. Inference Provenance

Each inference job records enough information to identify how the AI mask was produced:

- provider;
- engine/model name;
- model version or upstream identifier;
- inference-service version;
- explicit configuration values;
- source artifact IDs;
- source SHA-256 hashes;
- submitted, started, and completed timestamps;
- runtime seconds;
- GPU/device information when available;
- result segmentation SHA-256;
- failure category/message when applicable.

NeuroAnnotate must not make independent clinical-performance claims about DeepISLES merely because it integrates the model.

## 11. Annotation Model

v1.0 editing is intentionally simple:

- brush;
- erase;
- undo;
- redo;
- overlay opacity;
- slice navigation;
- brush-size control;
- a small set of keyboard shortcuts.

No interpolation or advanced 3D editing is included.

### 11.1 Dirty state

The frontend tracks whether the currently loaded mask differs from its loaded base revision or AI segmentation.

Changing case or revision while dirty requires explicit confirmation before discarding edits.

No autosave is used in v1.0.

### 11.2 Saving revisions

Saving a revision:

1. serializes the complete current binary mask;
2. validates it against DWI geometry;
3. writes a new immutable `.nii.gz` artifact;
4. calculates SHA-256;
5. computes edit statistics against the immediate parent/base mask;
6. stores the revision row;
7. clears the frontend dirty state only after persistence succeeds.

If persistence fails, the frontend retains the unsaved mask in memory.

### 11.3 Revision statistics

Revision metadata includes derived statistics such as:

- added voxels;
- removed voxels;
- changed voxels;
- total lesion voxels;
- lesion volume in mL.

These are descriptive mask statistics only, not clinical interpretations.

### 11.4 Revision lineage

A revision has one `parent_revision_id` and one source segmentation. Editing an older revision and saving creates a new child of that older revision. The data model therefore allows branching even if v1.0 uses only a simple timeline-style UI.

## 12. Export Model

Export operates only on a saved revision.

Creating an export:

```text
POST /api/cases/{case_id}/exports
```

Request body:

```json
{
  "revision_id": "..."
}
```

The backend creates:

```text
exports/<export-uuid>/
|-- lesion-mask.nii.gz
`-- provenance.json
```

The NIfTI mask is copied from the selected immutable revision rather than regenerated from browser state.

Required download endpoints:

```text
GET /api/exports/{id}/mask
GET /api/exports/{id}/provenance
GET /api/exports/{id}/bundle
```

The bundle is a ZIP containing standard NIfTI + JSON files. It is not a proprietary NeuroAnnotate format.

## 13. Provenance JSON Schema

Every export contains:

```json
{
  "schema": "neuroannotate.provenance",
  "schema_version": "1.0"
}
```

The schema must include the following logical sections.

### 13.1 Software

- NeuroAnnotate name;
- NeuroAnnotate version;
- source git commit when available.

### 13.2 Export

- export ID;
- creation timestamp.

### 13.3 Case

- case ID;
- annotation space = `DWI`.

### 13.4 Sources

For DWI, ADC, and FLAIR:

- artifact ID;
- SHA-256;
- shape;
- voxel spacing;
- datatype;
- affine.

Portable provenance excludes absolute paths and excludes original uploaded filenames by default to reduce accidental disclosure of patient identifiers.

### 13.5 AI segmentation

- segmentation artifact ID;
- segmentation SHA-256;
- inference job ID;
- provider;
- engine/model;
- model version;
- service version;
- timestamps;
- runtime;
- explicit configuration;
- runtime/device metadata.

### 13.6 Annotation

- exported revision ID;
- parent revision ID;
- revision timestamp;
- optional note;
- ordered revision-lineage IDs;
- edit summary.

The portable provenance does not embed every historical revision mask or every brush interaction.

### 13.7 Output

- output filename;
- SHA-256;
- datatype;
- label map (`0` background, `1` lesion);
- shape;
- voxel spacing;
- affine.

### 13.8 Disclaimer

The provenance contains a plain research-use disclaimer, for example:

> Research software only. Not for diagnosis or clinical decision-making.

## 14. User Interface and Workflow

The current three-area application layout remains:

```text
+--------------+---------------------------------------+-------------------+
| CASES        | MRI VIEWER                            | WORKFLOW          |
|              |                                       |                   |
| + New Case   | Axial / Sagittal / Coronal           | Case              |
| Case list    |                                       | AI Segmentation   |
|              |                                       | Annotation        |
|              |                                       | Revisions         |
|              |                                       | Export            |
+--------------+---------------------------------------+-------------------+
```

The right side is treated as one coherent workflow panel rather than unrelated controls.

### 14.1 New case flow

The user provides:

- case name;
- DWI `.nii` / `.nii.gz`;
- ADC `.nii` / `.nii.gz`;
- FLAIR `.nii` / `.nii.gz`.

Each modality displays validation feedback such as:

- valid NIfTI;
- dimensions;
- spacing;
- datatype;
- geometry mismatch information when relevant.

A native-geometry mismatch on FLAIR or ADC is informational, not an automatic error.

### 14.2 Viewer states

The UI clearly labels DWI as the annotation reference.

When a reference modality does not align with the DWI-space mask, the application states that segmentation overlay is unavailable in that geometry rather than silently displaying a misaligned overlay.

### 14.3 Inference states

Demo mode clearly states that the deterministic provider is not a trained medical model.

GPU mode displays:

- DeepISLES provider;
- GPU service availability;
- model identification;
- device;
- modality readiness.

Inference status is shown as:

- queued;
- running;
- completed;
- failed.

Technical details are available on demand without overwhelming the normal UI.

### 14.4 Annotation panel

The annotation panel shows:

- current base segmentation/revision;
- overlay opacity;
- brush/erase tool;
- brush size;
- unsaved edit counts;
- save-revision action.

### 14.5 Revision history

Revision history is presented as a simple timeline anchored at the AI segmentation. Selecting a historical revision loads that exact immutable mask.

The UI indicates the base/parent revision when editing from history.

### 14.6 Export panel

Export is disabled while unsaved edits exist.

For a saved revision, the panel shows:

- selected revision;
- output files;
- DWI native annotation space;
- mask SHA-256;
- create-export action.

After creation the user may:

- download bundle;
- download mask;
- view/download provenance.

### 14.7 System health

A restrained system-status control reports:

- backend;
- storage;
- database;
- GPU inference service;
- DeepISLES readiness;
- current mode (demo/GPU).

This is primarily for self-hosting diagnostics.

### 14.8 Empty states

The product must include clear empty states for:

- no cases;
- case with no segmentation;
- segmentation with no saved revisions.

## 15. Failure-Safe Persistence

Scientifically meaningful file writes use a temporary-write pattern where practical:

```text
write temp
  -> close/flush
  -> validate
  -> checksum
  -> atomic rename
  -> database commit
```

### 15.1 Import failure

No partial source artifact remains.

### 15.2 Inference failure

The job remains in history as failed and no segmentation artifact is created.

### 15.3 Invalid model output

This is recorded as an inference failure category distinct from a provider crash.

### 15.4 Revision failure

The browser retains unsaved state and does not mark the revision as saved.

### 15.5 Export failure

Temporary export files are removed and no completed export record is created.

## 16. Database Migration Strategy

v1.0 introduces Alembic migrations.

The existing MVP database is migrated rather than discarded. Users must not be instructed to delete `neuroannotate.db` as a normal upgrade procedure.

The implementation plan must define a migration from the current schema, including the existing case, modality, inference-run, and revision records, to the v1.0 schema.

CI must test migration from a representative current-MVP database fixture.

## 17. Testing Strategy

Testing has four layers.

### 17.1 Unit tests

Backend unit coverage includes:

- NIfTI metadata extraction;
- source/mask validation;
- affine comparison tolerance;
- SHA-256 calculation;
- path safety;
- inference state transitions;
- revision edit statistics;
- provenance generation;
- export checksums;
- provider response validation.

Frontend unit/component tests include:

- queued -> running -> completed inference states;
- failed job and retry flow;
- unsaved-change warnings;
- revision selection;
- export disabled while dirty;
- GPU unavailable state;
- geometry-mismatch messaging.

### 17.2 Backend integration tests

Using temporary SQLite and real generated NIfTI files:

```text
create case
-> import triad
-> create demo job
-> complete segmentation
-> save revisions
-> export
-> verify mask + provenance
```

### 17.3 Docker smoke tests

A deterministic synthetic case verifies that `docker compose up` produces a usable application and can execute the full demo workflow through export.

### 17.4 GPU integration validation

Real DeepISLES validation is not required on every hosted CI run.

A documented maintainer command such as:

```bash
make validate-gpu
```

must verify on a supported NVIDIA system:

- GPU service health;
- DeepISLES identification;
- inference completion;
- readable binary output;
- DWI-space geometry;
- provenance capture;
- successful NeuroAnnotate annotation/export round trip.

This validates integration, not clinical accuracy.

## 18. Deterministic Test Fixture

The repository includes a synthetic, non-patient integration fixture containing generated DWI, ADC, and FLAIR volumes plus an expected deterministic demo mask.

It is used to test:

- metadata extraction;
- hashes;
- geometry rules;
- revision statistics;
- export generation;
- provenance stability.

Real-model examples must use data under an appropriate license and are not committed merely for convenience.

## 19. CI Requirements

The existing GitHub Actions structure remains the base.

Every pull request must continue to run at minimum:

Backend:

- install;
- Ruff;
- pytest.

Frontend:

- install;
- lint/type checks;
- tests;
- production build.

v1.0 extends CI with:

- Alembic migration tests;
- deterministic end-to-end backend workflow tests;
- provenance schema validation;
- Docker configuration/smoke checks where practical.

Normal hosted CI remains CPU-only and does not download large DeepISLES model weights.

## 20. Release and Research-Software Readiness

v1.0 is released as:

```text
v1.0.0
```

The repository should contain at least:

- `README.md`;
- `CHANGELOG.md`;
- `CONTRIBUTING.md`;
- `CODE_OF_CONDUCT.md`;
- `CITATION.cff`;
- `SECURITY.md`;
- license and third-party attribution material;
- installation documentation;
- GPU setup documentation;
- architecture documentation;
- workflow documentation;
- provenance/export documentation;
- troubleshooting documentation.

The README stays concise and links to detailed documentation.

Model/runtime versions and other reproducibility-critical dependencies must be sufficiently pinned or identified in exported provenance.

Because JOSS policies and screening criteria can change, actual submission eligibility must be verified against current JOSS documentation when submission is considered. NeuroAnnotate should build a genuine public development and research-use history rather than treating software publication as a release-day checkbox.

If generative AI materially assists source code, documentation, or manuscript development, the project should maintain an `AI_USAGE.md` record so that future disclosure requirements can be satisfied accurately.

## 21. Security and Privacy Posture

v1.0 is local/self-hosted and has no telemetry requirement.

Portable exports must not include:

- absolute local paths;
- original filenames by default;
- other unnecessary host-specific metadata.

Uploaded NIfTI files are treated as untrusted input and validated before use.

The GPU service is intended to be reachable only on the private application network by default.

## 22. API Direction

Existing MVP routes may remain temporarily during migration, but the target v1.0 API should separate resources explicitly.

Representative endpoints:

```text
GET    /api/cases
POST   /api/cases
POST   /api/cases/{id}/modalities/{DWI|ADC|FLAIR}

POST   /api/cases/{id}/inference-jobs
GET    /api/inference-jobs/{job_id}
GET    /api/cases/{id}/inference-jobs

GET    /api/segmentations/{id}/file.nii.gz

GET    /api/cases/{id}/revisions
POST   /api/cases/{id}/revisions
GET    /api/revisions/{id}/file.nii.gz

POST   /api/cases/{id}/exports
GET    /api/exports/{id}/mask
GET    /api/exports/{id}/provenance
GET    /api/exports/{id}/bundle

GET    /api/health
GET    /api/inference/providers
```

Exact endpoint names may be refined in the implementation plan, but the resource boundaries in this specification are authoritative.

## 23. Compatibility and Migration Principles

Implementation must preserve the current working application's strengths:

- React/TypeScript/Vite frontend;
- Cornerstone3D multiplanar viewing;
- FastAPI backend;
- SQLAlchemy/SQLite persistence;
- local filesystem artifacts;
- deterministic demo mode;
- Docker Compose workflow.

The v1.0 work is an incremental architectural evolution, not a rewrite.

Existing runtime fixes for NIfTI loading and browser polyfills must be preserved.

## 24. Definition of Done

NeuroAnnotate v1.0 is ready only when a new researcher can start from a clean machine and, without touching source code:

```text
clone repository
-> start demo mode
-> create/import a case
-> view DWI / ADC / FLAIR
-> run segmentation
-> edit mask
-> save revision
-> reload revision
-> export mask + provenance
-> restart containers
-> verify cases/history still exist
```

On a supported NVIDIA system, the user must also be able to:

```text
start GPU profile
-> verify DeepISLES health
-> create a real inference job
-> receive a validated DWI-space mask
-> use the same annotation/revision/export workflow
```

The release is not blocked on DICOM, cloud deployment, authentication, collaboration, uncertainty estimation, or advanced editing.

## 25. Implementation Sequencing Constraints

The implementation plan should respect these dependencies:

1. introduce migration infrastructure and v1.0 persistence model;
2. harden managed artifacts, checksums, and validation;
3. implement persistent async job lifecycle with demo provider first;
4. implement export/provenance on the deterministic path;
5. update frontend workflow against those stable APIs;
6. add GPU inference-service contract and DeepISLES provider;
7. add Docker GPU profile and maintainer validation workflow;
8. complete release documentation and metadata.

This order keeps the application functional throughout development and avoids coupling UI work to an unstable real-model integration.

## 26. Architectural Decisions Summary

The following choices are explicitly approved for v1.0:

- research-software product, not clinical software;
- ischemic stroke focus;
- DWI + ADC + FLAIR input;
- NIfTI-only;
- DWI native space is canonical for all lesion masks;
- managed immutable source artifacts;
- SHA-256 for scientifically meaningful artifacts;
- DeepISLES behind a separate GPU inference service;
- Docker Compose GPU profile;
- asynchronous persistent SQLite jobs;
- one GPU job at a time;
- no automatic retry;
- complete immutable revision masks;
- simple 2D brush/erase/undo/redo editing;
- export = standard `.nii.gz` + provenance JSON;
- no proprietary export package;
- single-user/local v1.0;
- Alembic migrations;
- CPU CI plus explicit GPU integration validation;
- JOSS-ready engineering posture without premature publication claims.

## 27. Open Implementation Details

The design is complete. The following are implementation details to resolve in the implementation plan, not product decisions requiring another architecture round:

- exact SQLAlchemy model class names;
- exact affine comparison tolerance and helper implementation;
- exact polling interval and backoff;
- exact worker primitive used for the single local background worker;
- exact JSON schema validation library;
- exact ZIP response implementation;
- exact DeepISLES container/image version and model acquisition mechanism, subject to upstream distribution/licensing requirements;
- exact UI component/file decomposition;
- exact migration mechanics for existing MVP inference/revision rows.

These details must conform to the approved invariants in this specification.
