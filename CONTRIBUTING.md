# Contributing to NeuroAnnotate

Contributions that improve the reproducibility, safety, usability, testing, or documentation of
the local research workflow are welcome.

## Research scope

Keep changes within the single-user, local/self-hosted, NIfTI-only scope unless a proposal is
discussed first. Do not describe NeuroAnnotate as suitable for diagnosis, treatment, or clinical
decision-making, or imply validated-device status or established clinical accuracy. New data
collection or telemetry is out of scope unless it is explicitly proposed, reviewed, and made
opt-in.

## Development setup

Docker with Compose and `make` provide the supported full-stack path:

```bash
cp .env.example .env
make demo-data
make seed-demo
make dev
```

For local backend work, use Python 3.11 or newer:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
ruff check app tests
```

For frontend work, use Node.js 22:

```bash
cd frontend
npm ci
npm run lint
npm test -- --run
npm run build
```

For the lightweight DeepISLES service contract tests (no GPU or model weights required), use Python 3.8:

```bash
cd inference-service
python -m pip install -r requirements-test.txt
ruff check app tests
python -m pytest tests -q
```

## Changes and tests

- Open an issue before a large architectural or data-contract change.
- Add a focused regression test before fixing behavior and keep fixtures synthetic.
- Never commit participant data, NIfTI inputs, model weights, local databases, secrets, or host
  paths.
- Preserve the DWI-native geometry, immutable-revision, checksum, and portable-provenance
  contracts.
- Run `make verify`; use `bash scripts/smoke.sh` for the CPU end-to-end path.
- Treat `make validate-gpu` as a separate, explicit check requiring licensed inputs; see
  [docs/gpu.md](docs/gpu.md).

Submit a focused pull request describing the research-software impact, tests run, and any
limitations. Maintainers review and test accepted changes and retain responsibility for the
project. Compliance with a publication venue, including JOSS, must be evaluated against that
venue's then-current policy when submission is considered.

By participating, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report security
issues through the private process in [SECURITY.md](SECURITY.md), not a public issue containing
sensitive details.
