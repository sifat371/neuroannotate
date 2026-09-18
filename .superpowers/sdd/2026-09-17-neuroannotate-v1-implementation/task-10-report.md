# Task 10 report — optional GPU deployment

Base: `d49e8b3ed8b64dffa396fae5be2dc1e2f503b0b2`

## TDD evidence

- Backend RED: `../.venv/bin/pytest tests/test_health.py -v` collected four new
  contract tests and failed 4/4 on the absent `/api/health` alias and missing
  health payload fields. The failures were expected feature gaps, not test
  setup errors.
- Backend GREEN: the final focused health suite passed 6/6. It covers both
  aliases, demo mode without a network client, ready GPU facts, missing URL,
  transport failure, malformed/wrong-commit info, non-2xx service response,
  and storage/database degradation without exception/path disclosure.
- Frontend RED: `npm test -- --run tests/InferenceControls.test.tsx` failed 2
  new tests because inference was hardcoded to `demo`, DeepISLES identity was
  not rendered, and unavailable GPU mode did not disable submission.
- Frontend GREEN: `InferenceControls` and `SystemStatus` focused tests passed
  12/12. The existing demo disclaimer remains; a ready GPU mode submits
  `deepisles` through FastAPI, displays safe identity/device facts, and blocks
  unavailable GPU submission.

## Runtime/deployment behavior

- `/health` is preserved and `/api/health` is an identical alias. Both return
  bounded backend/storage/database diagnostics plus inference mode. Demo mode
  is healthy with `deepisles: not_enabled` and never calls the GPU service.
- Explicit `NEUROANNOTATE_INFERENCE_PROVIDER=deepisles` uses a two-second
  bounded private HTTP probe of `/health` and `/v1/info`, accepts only the
  pinned upstream commit, ready CUDA/device facts, and fails closed as
  `unavailable` without leaking exception details.
- Default `docker compose up` renders only frontend/backend, keeps provider
  mode `demo`, and has no NVIDIA requirement. The `gpu` profile adds an
  unported private `deepisles` service with NVIDIA reservation, healthcheck,
  and named `deepisles-model-cache` mounted at `/models`.
- The service startup invokes the preserved Task 9 integrity-checked source
  and MD5 fetch. It creates a completion marker only after atomic weight
  publication in the persistent cache, skips completed cache downloads, and
  does not start Uvicorn until the verified cache is present.
- `NEUROANNOTATE_HOST_DATA_DIR` selects the host data mount, defaulting to
  `./data`; the validator uses a `mktemp -d` directory and never references
  `/home/motion/neuroannotate/data/neuroannotate.db`.

## Validator and Make targets

- Added `make migrate` and `make validate-gpu`.
- `scripts/validate_gpu.sh` uses strict shell mode and refuses to run unless
  `NEUROANNOTATE_GPU_TEST_CASE` is an existing local directory with the exact
  DWI/ADC/FLAIR filenames. It uses a stable isolated Compose project, retains
  only the named weight cache, tears down validation containers/network, and
  removes its resolved temporary data directory.
- If explicitly supplied licensed data, it validates pinned service info,
  async backend job completion, DWI geometry/binary `uint8` mask, no-op
  revision/export, exact ZIP members, and DeepISLES provenance.

## Verification

- `docker compose config >/dev/null` — passed.
- `docker compose --profile gpu config >/dev/null` — passed; rendered contract
  checks confirmed no DeepISLES host port, named `/models` cache, NVIDIA GPU
  reservation, and backend private URL.
- `cd backend && ../.venv/bin/pytest tests/test_health.py -v` — 6 passed.
- `cd backend && ../.venv/bin/pytest -q` — 103 passed (two pre-existing
  TestClient dependency warnings).
- `cd backend && ../.venv/bin/ruff check app tests` — passed.
- `cd frontend && npm test -- --run` — 47 passed.
- `cd frontend && npm run lint` — passed.
- `cd frontend && npm run build` — passed; existing Vite direct-`eval` and
  chunk-size warnings remained.
- `bash -n scripts/validate_gpu.sh` and
  `bash -n inference-service/scripts/fetch_weights.sh` — passed.
- Validator no-input safety preflight exited 2 before Docker activity, with
  the expected licensed-triad requirement message.
- `pytest inference-service/tests/test_api_contract.py -v` — 9 passed.
- `git diff --check` and base-to-HEAD diff checks — passed before commit.

## Real GPU status

Real GPU/DeepISLES validation was **not run**. No
`NEUROANNOTATE_GPU_TEST_CASE` licensed local triad was provided, and this task
did not start the GPU profile, download weights, build a GPU image, or execute
the model.
