#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

cleanup() {
  rm -f data/smoke-segmentation.nii.gz data/smoke-labelmap.bin data/smoke-shape.json data/smoke-export.nii.gz
}
trap cleanup EXIT

printf 'Checking API health...\n'
curl -fsS "$API_BASE/health" | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["status"]=="ok"'

printf 'Locating seeded demo case...\n'
CASE_ID="$(curl -fsS "$API_BASE/api/cases" | python3 -c 'import json,sys; xs=json.load(sys.stdin); print(next(x["id"] for x in xs if x["name"]=="NeuroAnnotate Demo" and x["ready_for_inference"]))')"

printf 'Running deterministic demo segmentation...\n'
RUN_JSON="$(curl -fsS -X POST "$API_BASE/api/cases/$CASE_ID/segment")"
INFERENCE_ID="$(printf '%s' "$RUN_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
curl -fsS "$API_BASE/api/cases/$CASE_ID/segmentations/latest/file" -o data/smoke-segmentation.nii.gz

printf 'Preparing unchanged editable labelmap payload...\n'
docker compose exec -T backend python - <<'PY'
from pathlib import Path
import json
import numpy as np
from app.services.nifti_codec import load_volume

volume = load_volume(Path('/app/data/smoke-segmentation.nii.gz'))
mask = (volume.data > 0).astype(np.uint8)
Path('/app/data/smoke-labelmap.bin').write_bytes(mask.reshape(-1, order='F').tobytes())
Path('/app/data/smoke-shape.json').write_text(json.dumps(list(mask.shape)))
PY
SHAPE="$(cat data/smoke-shape.json)"

printf 'Saving immutable revision...\n'
REV_JSON="$(curl -fsS -X POST "$API_BASE/api/cases/$CASE_ID/revisions" \
  -F "voxels=@data/smoke-labelmap.bin;type=application/octet-stream" \
  -F "shape=$SHAPE" \
  -F "source_inference_id=$INFERENCE_ID" \
  -F "note=Smoke test unchanged labelmap")"
REVISION_ID="$(printf '%s' "$REV_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

printf 'Exporting revision and validating geometry...\n'
curl -fsS "$API_BASE/api/cases/$CASE_ID/export?revision_id=$REVISION_ID" -o data/smoke-export.nii.gz
docker compose exec -T backend python - <<'PY'
from pathlib import Path
from app.services.nifti_codec import load_volume

exported = load_volume(Path('/app/data/smoke-export.nii.gz'))
dwi = next(Path('/app/data/cases').glob('*/modalities/dwi.nii*'))
reference = load_volume(dwi)
assert exported.data.shape == reference.data.shape, (exported.data.shape, reference.data.shape)
assert exported.affine.shape == reference.affine.shape
print(f'Valid export: shape={exported.data.shape}')
PY

printf 'NeuroAnnotate smoke workflow passed.\n'
