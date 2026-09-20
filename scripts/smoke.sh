#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/neuroannotate-smoke.XXXXXX")"
SMOKE_TOKEN="$(basename "$SMOKE_DIR")"
CONTAINER_DIR="/tmp/$SMOKE_TOKEN"
cd "$ROOT_DIR"

cleanup() {
  docker compose exec -T backend python - "$CONTAINER_DIR" >/dev/null 2>&1 <<'PY' || true
import shutil
import sys

shutil.rmtree(sys.argv[1], ignore_errors=True)
PY
  rm -rf "$SMOKE_DIR"
}
trap cleanup EXIT

printf 'Checking API health...\n'
curl -fsS "$API_BASE/health" \
  | python3 -c 'import json,sys; assert json.load(sys.stdin)["status"] == "ok"'

printf 'Generating a synthetic non-patient source triad...\n'
docker compose exec -T backend python - "$CONTAINER_DIR" <<'PY'
import sys
from pathlib import Path

from app.scripts.generate_demo_data import generate_demo_case

generate_demo_case(Path(sys.argv[1]))
PY
for filename in demo_dwi.nii.gz demo_adc.nii.gz demo_flair.nii.gz; do
  docker compose cp "backend:$CONTAINER_DIR/$filename" "$SMOKE_DIR/$filename" >/dev/null
done

printf 'Importing the generated triad atomically...\n'
CASE_JSON="$(curl -fsS -X POST "$API_BASE/api/cases" \
  -F "name=NeuroAnnotate HTTP smoke $SMOKE_TOKEN" \
  -F "dwi=@$SMOKE_DIR/demo_dwi.nii.gz;type=application/gzip" \
  -F "adc=@$SMOKE_DIR/demo_adc.nii.gz;type=application/gzip" \
  -F "flair=@$SMOKE_DIR/demo_flair.nii.gz;type=application/gzip")"
CASE_ID="$(printf '%s' "$CASE_JSON" \
  | python3 -c 'import json,sys; value=json.load(sys.stdin); assert value["ready_for_inference"]; print(value["id"])')"

printf 'Queueing deterministic demo inference...\n'
JOB_JSON="$(curl -fsS -X POST "$API_BASE/api/cases/$CASE_ID/inference-jobs" \
  -H 'Content-Type: application/json' \
  -d '{"provider":"demo"}')"
JOB_ID="$(printf '%s' "$JOB_JSON" \
  | python3 -c 'import json,sys; value=json.load(sys.stdin); assert value["status"] == "queued"; print(value["id"])')"

printf 'Waiting for persisted inference completion...\n'
JOB_STATUS="queued"
for _attempt in $(seq 1 120); do
  JOB_JSON="$(curl -fsS "$API_BASE/api/inference-jobs/$JOB_ID")"
  JOB_STATUS="$(printf '%s' "$JOB_JSON" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  if [[ "$JOB_STATUS" == "completed" ]]; then
    break
  fi
  if [[ "$JOB_STATUS" == "failed" ]]; then
    printf 'Inference job failed: %s\n' "$JOB_JSON" >&2
    exit 1
  fi
  sleep 0.25
done
if [[ "$JOB_STATUS" != "completed" ]]; then
  printf 'Inference job did not complete before the smoke timeout.\n' >&2
  exit 1
fi
SEGMENTATION_ID="$(printf '%s' "$JOB_JSON" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["segmentation_id"])')"

printf 'Downloading and validating the segmentation...\n'
curl -fsS "$API_BASE/api/segmentations/$SEGMENTATION_ID/file.nii.gz" \
  -o "$SMOKE_DIR/segmentation.nii.gz"
docker compose cp "$SMOKE_DIR/segmentation.nii.gz" \
  "backend:$CONTAINER_DIR/segmentation.nii.gz" >/dev/null
docker compose exec -T backend python - "$CONTAINER_DIR" <<'PY'
import json
import sys
from pathlib import Path

import numpy as np

from app.services.nifti_codec import load_volume

root = Path(sys.argv[1])
segmentation = load_volume(root / "segmentation.nii.gz")
expected = load_volume(root / "demo_mask.nii.gz")
np.testing.assert_array_equal(segmentation.data, expected.data)
np.testing.assert_allclose(segmentation.affine, expected.affine, atol=1e-6, rtol=0)
mask = segmentation.data.astype(np.uint8)
(root / "labelmap.bin").write_bytes(mask.reshape(-1, order="F").tobytes())
(root / "shape.json").write_text(json.dumps(list(mask.shape)), encoding="utf-8")
PY
docker compose cp "backend:$CONTAINER_DIR/labelmap.bin" "$SMOKE_DIR/labelmap.bin" >/dev/null
docker compose cp "backend:$CONTAINER_DIR/shape.json" "$SMOKE_DIR/shape.json" >/dev/null
SHAPE="$(<"$SMOKE_DIR/shape.json")"

printf 'Saving a no-op immutable revision...\n'
REVISION_JSON="$(curl -fsS -X POST "$API_BASE/api/cases/$CASE_ID/revisions" \
  -F "voxels=@$SMOKE_DIR/labelmap.bin;type=application/octet-stream" \
  -F "shape=$SHAPE" \
  -F "source_segmentation_id=$SEGMENTATION_ID" \
  -F "note=HTTP smoke no-op revision")"
REVISION_ID="$(printf '%s' "$REVISION_JSON" \
  | python3 -c 'import json,sys; value=json.load(sys.stdin); stats=value["edit_stats"]; assert stats["changed_voxels"] == 0; print(value["id"])')"

printf 'Creating and verifying the standard export bundle...\n'
EXPORT_JSON="$(curl -fsS -X POST "$API_BASE/api/cases/$CASE_ID/exports" \
  -H 'Content-Type: application/json' \
  -d "{\"revision_id\":\"$REVISION_ID\"}")"
BUNDLE_URL="$(printf '%s' "$EXPORT_JSON" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["bundle_url"])')"
curl -fsS "$API_BASE$BUNDLE_URL" -o "$SMOKE_DIR/export.zip"
python3 - "$SMOKE_DIR/export.zip" <<'PY'
import json
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    names = archive.namelist()
    assert len(names) == 2
    assert set(names) == {"lesion-mask.nii.gz", "provenance.json"}
    provenance = json.loads(archive.read("provenance.json"))
    assert provenance["case"]["annotation_space"] == "DWI"
    assert provenance["output"]["shape"] == [64, 64, 48]
    assert provenance["output"]["spacing"] == [1.5, 1.5, 2.0]
PY

printf 'PASS\n'
