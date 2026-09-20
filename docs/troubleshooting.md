# Troubleshooting

## The app does not start

Run `docker compose config` first, then inspect `docker compose ps` and
`docker compose logs backend frontend`. Port 5173 is the frontend and port 8000 is the API. If
either port is occupied, stop the conflicting service or adjust the Compose mapping. The
frontend waits for backend health.

## The demo case is absent

Generate and seed it before starting the normal workflow:

```bash
make demo-data
make seed-demo
docker compose up --build
```

Generated sample volumes are synthetic and ignored by git. Seeding is separate from normal
application startup.

## An import is rejected

Upload exactly one DWI, ADC, and FLAIR. Each must be a readable, non-empty 3D numeric `.nii` or
`.nii.gz` volume with finite geometry and must fit the configured upload limit. The import is
atomic, so correct the rejected input and submit the complete triad again; a partial case should
not remain.

## Inference is queued or failed

Refresh `/api/health` and inspect the job failure category/message. Active jobs are processed by
the backend's sequential local worker. A restart converts an interrupted `running` job to
`failed`; use Retry to create a new attempt. In demo mode, confirm the complete immutable source
triad is still present. For GPU mode, follow [gpu.md](gpu.md).

## Images or overlays do not load

Use the current frontend build and browser console/network log. NeuroAnnotate serves NIfTI
files through API URLs, including `.nii.gz` paths required by the volume loader. Confirm the API
request succeeds, then verify the mask is binary `uint8` and has DWI shape/affine. v1 does not
register or resample incompatible geometry.

## Save or export is disabled

A completed segmentation must be loaded before the first revision can be saved. Save the full
annotation revision after edits. Export requires a selected saved revision and is deliberately
disabled while the workspace is dirty, so save or discard the pending edits first.

## Local verification fails

Install backend development dependencies and frontend packages, then run focused commands from
their directories. The complete gate is:

```bash
make verify
```

The CPU end-to-end check is `bash scripts/smoke.sh`. It uses isolated temporary runtime data;
do not point test commands at a working research database. GPU validation is separate and
requires licensed inputs as described in [gpu.md](gpu.md).
