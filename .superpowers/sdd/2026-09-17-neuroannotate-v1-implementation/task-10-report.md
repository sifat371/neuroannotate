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

## Fix round 1

### Review-finding mapping

1. The validator now retries the actual `/v1/info` payload until it reports the
   pinned commit, CUDA, a non-empty device, and `ready: true`. The helper
   deadline also bounds every info request and sleep during first-boot weight
   population. Sourced helpers initialize their own repository path.
2. Job polling now uses a `SECONDS` wall-clock deadline of exactly 1800 seconds.
   Each curl timeout and sleep is capped to the remaining time; transient curl
   failures are retried within that same deadline instead of terminating under
   `set -e`.
3. Failed-job Retry is disabled when configured inference is unavailable, and
   the handler has the same guard so programmatic invocation cannot bypass the
   disabled state.
4. Database health uses one daemon worker, waits at most 50 ms per request,
   caches completed results briefly, and never queues additional workers while
   a driver call is stalled. Unexpected worker exceptions publish an
   unavailable result and release the in-flight state.
5. Health reports configured `nnunet` as explicit legacy mode and reserves
   unknown mode for unrecognized configuration. Neither mode is presented as
   demo or available in inference controls.
6. Regression coverage now exercises readiness retry/deadline behavior,
   transient polling failures, total wall-clock expiration, disabled Retry,
   legacy versus unknown modes, bounded database waiting, and database worker
   recovery.

### TDD and mutation evidence

The interrupted implementer's original RED output was lost when its external
quota ended, so no RED is claimed for changes already present at takeover.
Their existing fixes were instead checked by mutation: bypassing readiness
validation made the helper accept unready info; removing bounded sleeping broke
the deadline assertion; removing Retry's disabled state failed the UI test;
collapsing `nnunet` into unknown failed the health contract; and removing the
database wait timeout failed the bounded-return test.

The takeover audit found four still-missing corrections and captured genuine
RED before production edits:

- the database recovery test failed because `RuntimeError` killed the worker
  and left the next probe false, with an unhandled-thread warning;
- the legacy/unknown UI cases failed because both still rendered demo copy;
- the sourced helper suite exited 127 on an unbound `repo_dir`;
- after repository initialization was fixed, a traced helper run exited at the
  first failed `fetch_job_status` command substitution under `set -e`.

After the minimal fixes, focused GREEN was 9/9 backend health tests, 15/15
inference/status frontend tests, and a passing validator helper suite plus shell
syntax checks.

### Files changed in the fix

- `backend/app/api/routes/health.py`
- `backend/tests/test_health.py`
- `frontend/src/features/inference/InferenceControls.tsx`
- `frontend/src/types/api.ts`
- `frontend/tests/InferenceControls.test.tsx`
- `scripts/validate_gpu.sh`
- `scripts/tests/test_validate_gpu_helpers.sh`

### Verification

- `cd backend && ../.venv/bin/pytest tests/test_health.py -v` — 9 passed.
- `cd backend && ../.venv/bin/pytest -q` — 106 passed with the same two
  dependency deprecation warnings.
- `cd backend && ../.venv/bin/ruff check app tests` — passed.
- `cd frontend && npm test -- --run` — 50 passed.
- `cd frontend && npm run lint` — passed.
- `cd frontend && npm run build` — passed with the existing Vite direct-eval
  and chunk-size warnings.
- `.venv/bin/pytest inference-service/tests/test_api_contract.py -v` — 9
  passed with the same two dependency deprecation warnings.
- `.venv/bin/ruff check inference-service/app inference-service/tests` —
  passed.
- `bash scripts/tests/test_validate_gpu_helpers.sh` — passed.
- `bash -n` for the validator, helper test, and weight-fetch script — passed.
- Default and GPU-profile Compose config rendering — passed. JSON assertions
  confirmed default services are only backend/frontend with demo mode, while
  GPU config has the private unported service, named `/models` cache, NVIDIA
  reservation, and private backend URL.
- Validator no-input preflight exited 2 with the licensed-triad requirement
  before any Docker action, as intended.
- `git diff --check` — passed.

One service-suite invocation initially used `../.venv` from the repository root
and failed to find pytest; the corrected `.venv/bin/pytest` command above
passed. One custom Compose JSON assertion initially assumed an optional
`nocopy` key; the corrected semantic assertion above passed against the
rendered schema.

### Self-review and residual limits

The database driver call itself cannot be force-cancelled safely, but only one
daemon probe may remain blocked and every health request returns within its
50 ms wait bound. The validator helper tests use controlled fake service/job
responses and one real 1.1-second elapsed-time check; no real container, model,
weight download, or clinical data was used. The real GPU validation status
therefore remains unchanged: not run because no licensed test triad was
provided.
