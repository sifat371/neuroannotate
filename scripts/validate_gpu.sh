#!/usr/bin/env bash
set -euo pipefail

# Validate the optional DeepISLES integration with caller-supplied licensed data.
test_case="${NEUROANNOTATE_GPU_TEST_CASE:-}"
if [[ -z "$test_case" || ! -d "$test_case" ]]; then
    echo "NEUROANNOTATE_GPU_TEST_CASE must name an existing licensed triad directory" >&2
    exit 2
fi
for filename in dwi.nii.gz adc.nii.gz flair.nii.gz; do
    if [[ ! -f "${test_case}/${filename}" ]]; then
        echo "NEUROANNOTATE_GPU_TEST_CASE must contain dwi.nii.gz, adc.nii.gz, and flair.nii.gz" >&2
        exit 2
    fi
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
cd "$repo_dir"

project="neuroannotate-gpu-validate"
temporary_data="$(mktemp -d -t neuroannotate-gpu-validation.XXXXXX)"
compose=(docker compose -p "$project" --profile gpu)
cleanup() {
    "${compose[@]}" down --remove-orphans >/dev/null 2>&1 || true
    rm -rf -- "$temporary_data"
}
trap cleanup EXIT

export NEUROANNOTATE_HOST_DATA_DIR="$temporary_data"
export NEUROANNOTATE_INFERENCE_PROVIDER="deepisles"
export NEUROANNOTATE_DEEPISLES_URL="http://deepisles:8080"

wait_for_url() {
    local url="$1"
    local attempts="$2"
    local attempt
    for ((attempt = 1; attempt <= attempts; attempt += 1)); do
        if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; then
            return 0
        fi
        sleep 3
    done
    echo "Timed out waiting for required validation service" >&2
    return 1
}

json_field() {
    local field="$1"
    "${repo_dir}/.venv/bin/python" -c \
        "import json, sys; print(json.load(sys.stdin)${field})"
}

"${compose[@]}" up -d --build
wait_for_url "http://localhost:8000/api/health" 40

service_info="$("${compose[@]}" exec -T deepisles python3.8 -c \
    "import json, urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://localhost:8080/v1/info', timeout=5))))")"
printf '%s' "$service_info" | "${repo_dir}/.venv/bin/python" -c '
import json
import sys
info = json.load(sys.stdin)
assert info["upstream_commit"] == "7658b608fc0d890cf14448ff3e58c47ad5c761e7"
assert info["cuda_available"] is True
assert isinstance(info["device"], str) and info["device"]
assert info["ready"] is True
'

case_json="${temporary_data}/case.json"
curl --fail --silent --show-error --max-time 120 \
    -F 'name=GPU validation case' \
    -F "dwi=@${test_case}/dwi.nii.gz;type=application/gzip" \
    -F "adc=@${test_case}/adc.nii.gz;type=application/gzip" \
    -F "flair=@${test_case}/flair.nii.gz;type=application/gzip" \
    http://localhost:8000/api/cases >"$case_json"
case_id="$(json_field "['id']" <"$case_json")"

job_json="${temporary_data}/job.json"
curl --fail --silent --show-error --max-time 30 \
    -H 'Content-Type: application/json' \
    --data '{"provider":"deepisles"}' \
    "http://localhost:8000/api/cases/${case_id}/inference-jobs" >"$job_json"
job_id="$(json_field "['id']" <"$job_json")"

for ((attempt = 1; attempt <= 360; attempt += 1)); do
    curl --fail --silent --show-error --max-time 15 \
        "http://localhost:8000/api/inference-jobs/${job_id}" >"$job_json"
    job_status="$(json_field "['status']" <"$job_json")"
    if [[ "$job_status" == "completed" ]]; then
        break
    fi
    if [[ "$job_status" == "failed" ]]; then
        echo "DeepISLES job failed during validation" >&2
        exit 1
    fi
    sleep 5
done
if [[ "${job_status:-}" != "completed" ]]; then
    echo "DeepISLES job did not complete within 30 minutes" >&2
    exit 1
fi

segmentation_id="$(json_field "['segmentation_id']" <"$job_json")"
segmentation_path="${temporary_data}/segmentation.nii.gz"
curl --fail --silent --show-error --max-time 120 \
    "http://localhost:8000/api/segmentations/${segmentation_id}/file.nii.gz" >"$segmentation_path"

voxels_path="${temporary_data}/voxels.bin"
shape="$("${repo_dir}/.venv/bin/python" - "$segmentation_path" "$voxels_path" <<'PY'
import json
import sys

import nibabel as nib
import numpy as np

image = nib.load(sys.argv[1])
data = np.asanyarray(image.dataobj)
assert data.dtype == np.dtype("uint8")
assert data.ndim == 3
data.ravel(order="F").tofile(sys.argv[2])
print(json.dumps(list(data.shape)))
PY
)"

revision_json="${temporary_data}/revision.json"
curl --fail --silent --show-error --max-time 120 \
    -F "voxels=@${voxels_path};type=application/octet-stream" \
    -F "shape=${shape}" \
    -F "source_segmentation_id=${segmentation_id}" \
    "http://localhost:8000/api/cases/${case_id}/revisions" >"$revision_json"
revision_id="$(json_field "['id']" <"$revision_json")"

export_json="${temporary_data}/export.json"
curl --fail --silent --show-error --max-time 120 \
    -H 'Content-Type: application/json' \
    --data "{\"revision_id\":\"${revision_id}\"}" \
    "http://localhost:8000/api/cases/${case_id}/exports" >"$export_json"
export_id="$(json_field "['id']" <"$export_json")"
bundle_path="${temporary_data}/export.zip"
mask_path="${temporary_data}/export-mask.nii.gz"
provenance_path="${temporary_data}/provenance.json"
curl --fail --silent --show-error --max-time 120 \
    "http://localhost:8000/api/exports/${export_id}/bundle" >"$bundle_path"
curl --fail --silent --show-error --max-time 120 \
    "http://localhost:8000/api/exports/${export_id}/mask" >"$mask_path"
curl --fail --silent --show-error --max-time 120 \
    "http://localhost:8000/api/exports/${export_id}/provenance" >"$provenance_path"

"${repo_dir}/.venv/bin/python" - "$test_case/dwi.nii.gz" "$mask_path" "$bundle_path" "$provenance_path" <<'PY'
import json
import sys
import zipfile

import nibabel as nib
import numpy as np

dwi = nib.load(sys.argv[1])
mask = nib.load(sys.argv[2])
mask_data = np.asanyarray(mask.dataobj)
assert mask_data.dtype == np.dtype("uint8")
assert mask_data.ndim == 3
assert np.isfinite(mask_data).all()
assert np.isin(mask_data, (0, 1)).all()
assert mask.shape == dwi.shape
assert np.allclose(mask.affine, dwi.affine, atol=1e-5, rtol=0)
with zipfile.ZipFile(sys.argv[3]) as bundle:
    assert set(bundle.namelist()) == {"lesion-mask.nii.gz", "provenance.json"}
with open(sys.argv[4], encoding="utf-8") as stream:
    provenance = json.load(stream)
assert provenance["ai_segmentation"]["provider"] == "deepisles"
assert provenance["ai_segmentation"]["model_version"] == "7658b608fc0d890cf14448ff3e58c47ad5c761e7"
PY

echo "PASS: DeepISLES GPU validation completed"
