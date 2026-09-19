# v1 workflow

NeuroAnnotate is a single-user, local/self-hosted, NIfTI-only research workflow. It has no
telemetry, authentication, collaboration, DICOM, or PACS integration. It is not a medical device
and is not for diagnosis, treatment, or clinical decision-making.

## 1. Import an atomic source triad

A case is created by one multipart request containing a non-empty case name and exactly one
`dwi`, `adc`, and `flair` upload. Each upload must be a readable, non-empty, three-dimensional
numeric NIfTI with a finite 4×4 affine and finite voxel spacing, within the configured upload
limit. `.nii` and `.nii.gz` inputs are accepted; uncompressed inputs are normalized to `.nii.gz`
for managed storage.

The backend stages and validates all three files before publishing the case. If any validation,
filesystem, or database step fails, the case record and staged/final artifacts are rolled back.
Successful source artifacts are immutable and record their managed-byte SHA-256, geometry,
datatype, size, and original filename. Original filenames are local metadata and are excluded
from portable export provenance.

DWI defines the canonical annotation geometry. v1 does not register or resample modalities.

## 2. Run persisted asynchronous inference

The UI selects the deterministic `demo` provider in the default CPU configuration or
`deepisles` when the backend is configured for the GPU provider. A submission snapshots the
three immutable source artifact IDs and SHA-256 values and returns immediately.

Jobs persist these states:

```text
queued -> running -> completed
                  -> failed
queued ----------------> failed
```

Only a completed job has a segmentation artifact. The sequential local worker verifies the
snapshotted source identities/checksums, validates provider output as binary `uint8` in DWI
geometry, and atomically persists it. A failure remains persisted with a category and message;
partial output is removed. A job left `running` by an application restart is recovered as
`failed` with category `application_interrupted`.

There is no automatic retry. Retry is available only for a failed job and creates a new queued
job with a new ID; the failed attempt remains unchanged for auditability. The browser polls
active jobs and exposes the completed mask or failure.

## 3. Review and edit

The browser displays axial, sagittal, and coronal views with modality switching, navigation,
window/level, and a segmentation overlay. Brush and erase operations modify the in-memory
binary labelmap; undo and redo operate on that editing history.

Loading an inference mask or saved revision establishes a clean base. Any edit marks the
workspace dirty. Loading another saved revision while dirty prompts before discarding unsaved
changes; selecting a different case clears the current edit state.

## 4. Save immutable revisions

Saving transmits the complete x-fastest labelmap byte buffer and its three-dimensional shape.
The backend reconstructs it in Fortran order, binarizes it, verifies DWI shape/affine/spacing,
and saves a new `uint8` NIfTI. A revision is never overwritten.

The first revision points to its source segmentation. A later revision points to its immediate
parent and keeps the same source-segmentation lineage. A note is optional. Saving clears the
dirty flag and makes the new revision the editing base. Edit statistics compare the saved mask
with that immediate base and are descriptive mask statistics only; see
[provenance.md](provenance.md).

## 5. Export a saved revision

Export is disabled until a revision has been saved and while the workspace is dirty. The portable
v1 export is created with POST `/api/cases/{case_id}/exports`, which copies the selected immutable
revision into a new immutable snapshot only after checking source, segmentation, and revision
SHA-256 values.

Each export provides:

- `/api/exports/{export_id}/mask`, serving `lesion-mask.nii.gz`, a binary `uint8` mask in
  canonical DWI-native geometry;
- `/api/exports/{export_id}/provenance`, serving `provenance.json`, validated against the
  committed v1 schema; and
- `/api/exports/{export_id}/bundle`, serving `neuroannotate-export.zip`, containing exactly
  those two files.

The compatibility GET `/api/cases/{case_id}/export?revision_id=...` route returns only the raw
saved revision NIfTI. It is not a portable provenance bundle and does not include
`provenance.json` or the two-file ZIP.

See [provenance.md](provenance.md) for field and portability semantics.
