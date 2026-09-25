#!/usr/bin/env bash
set -euo pipefail

test_repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
validator_path="${test_repo_dir}/scripts/validate_gpu.sh"
unset repo_dir
VALIDATE_GPU_SOURCE_ONLY=1 source "$validator_path"

ready_info='{"upstream_commit":"BrainLesion/stroke_segmentor@0.0.3","model_version":"stroke-segmentor-0.0.3","cuda_available":true,"device":"cuda:0","ready":true}'
invalid_info='{"upstream_commit":"wrong","model_version":"wrong","cuda_available":false,"device":"","ready":false}'
printf '%s' "$ready_info" | deepisles_info_ready
if printf '%s' "$invalid_info" | deepisles_info_ready; then
    echo "invalid DeepISLES info was accepted" >&2
    exit 1
fi

temporary_log="$(mktemp)"
cleanup_test() { rm -f -- "$temporary_log"; }
trap cleanup_test EXIT
fetch_service_info() { printf '%s' "$invalid_info"; }
sleep() { printf '%s\n' "$1" >>"$temporary_log"; SECONDS=$((SECONDS + $1)); }
SECONDS=0
if wait_for_deepisles_info 5 2>/dev/null; then
    echo "unready service unexpectedly passed validation" >&2
    exit 1
fi
test "$(head -n 1 "$temporary_log")" = "3"
second_sleep="$(sed -n '2p' "$temporary_log")"
[[ -z "$second_sleep" || "$second_sleep" == "1" || "$second_sleep" == "2" ]]

: >"$temporary_log"
attempt_file="$(mktemp)"
cleanup_attempt() { rm -f -- "$attempt_file"; }
trap 'cleanup_test; cleanup_attempt' EXIT
printf '0\n' >"$attempt_file"
fetch_service_info() {
    attempt="$(cat "$attempt_file")"
    attempt=$((attempt + 1))
    printf '%s\n' "$attempt" >"$attempt_file"
    if ((attempt == 1)); then
        printf '%s' "$invalid_info"
    else
        printf '%s' "$ready_info"
    fi
}
SECONDS=0
wait_for_deepisles_info 10
test "$(cat "$attempt_file")" = "2"
test "$(tr '\n' ' ' <"$temporary_log")" = "3 "

: >"$temporary_log"
fetch_job_status() { printf 'queued\n'; }
SECONDS=0
if wait_for_completed_job ignored 4 2>/dev/null; then
    echo "queued job unexpectedly completed" >&2
    exit 1
fi
test "$(tr '\n' ' ' <"$temporary_log")" = "4 "

: >"$temporary_log"
printf '0\n' >"$attempt_file"
fetch_job_status() {
    attempt="$(cat "$attempt_file")"
    attempt=$((attempt + 1))
    printf '%s\n' "$attempt" >"$attempt_file"
    if ((attempt == 1)); then
        return 1
    fi
    printf 'completed\n'
}
SECONDS=0
wait_for_completed_job ignored 10
test "$(cat "$attempt_file")" = "2"
test "$(tr '\n' ' ' <"$temporary_log")" = "5 "

: >"$temporary_log"
printf '0\n' >"$attempt_file"
fetch_job_status() {
    attempt="$(cat "$attempt_file")"
    attempt=$((attempt + 1))
    printf '%s\n' "$attempt" >"$attempt_file"
    command sleep 1.1
    printf 'queued\n'
}
SECONDS=0
if wait_for_completed_job ignored 1 2>/dev/null; then
    echo "queued job unexpectedly completed after its wall-clock deadline" >&2
    exit 1
fi
test "$(cat "$attempt_file")" = "1"
test ! -s "$temporary_log"

# The validator must not require a repository-local virtualenv just to parse JSON.
unset VALIDATE_GPU_PYTHON
expected_python="$(command -v python3 || command -v python)"
test "$(validation_python)" = "$expected_python"
VALIDATE_GPU_PYTHON=/custom/python
export VALIDATE_GPU_PYTHON
test "$(validation_python)" = "/custom/python"
unset VALIDATE_GPU_PYTHON

# Cleanup is allowed only for the mktemp namespace used by this validator.
is_safe_validation_temp_root /tmp/neuroannotate-gpu-validation.ABC123
if is_safe_validation_temp_root /tmp/not-neuroannotate; then
    echo "unsafe temporary root was accepted" >&2
    exit 1
fi
if is_safe_validation_temp_root /; then
    echo "filesystem root was accepted for cleanup" >&2
    exit 1
fi

# The implementation must perform container-side cleanup before host removal,
# because normal container-created case directories may be root-owned and 0700.
grep -q 'exec -T backend python' "$validator_path"
grep -q "Path('/app/data')" "$validator_path"
if grep -q '\.venv/bin/python' "$validator_path"; then
    echo "validator still hardcodes the repository virtualenv" >&2
    exit 1
fi

VALIDATE_GPU_PYTHON=/definitely/missing/python
export VALIDATE_GPU_PYTHON
if require_validation_python 2>/dev/null; then
    echo "missing validation interpreter passed preflight" >&2
    exit 1
fi
unset VALIDATE_GPU_PYTHON
