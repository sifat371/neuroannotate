#!/usr/bin/env bash
set -euo pipefail

url='https://zenodo.org/records/14026715/files/stroke_ensemble_weights.7z?download=1'
expected='be5b6dfcd66b55c2e6dc6db9a5880f7f'
models_dir='/models'
repo_dir='/opt/deepisles'
weights_dir="${models_dir}/weights"
ready_marker="${models_dir}/.neuroannotate-weights-ready"
mkdir -p "$models_dir"
test -d "$repo_dir"
if [[ -f "$ready_marker" && -d "$weights_dir" ]]; then
    exit 0
fi
rm -f "$ready_marker"
archive_tmp="$(mktemp "${models_dir}/.stroke_ensemble_weights.XXXXXX.7z")"
extract_tmp="$(mktemp -d "${models_dir}/.weights-extract.XXXXXX")"
cleanup() {
    rm -f "$archive_tmp"
    rm -rf "$extract_tmp"
}
trap cleanup EXIT

curl --fail --location --retry 3 --output "$archive_tmp" "$url"
printf '%s  %s\n' "$expected" "$archive_tmp" | md5sum --check --status
7z x "$archive_tmp" "-o${extract_tmp}" -y >/dev/null
test -d "${extract_tmp}/weights"
rm -rf "$weights_dir"
mv "${extract_tmp}/weights" "$weights_dir"
touch "$ready_marker"
