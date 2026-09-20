# NeuroAnnotate

NeuroAnnotate is a single-user, local/self-hosted research workspace for importing a
DWI/ADC/FLAIR NIfTI triad, generating a lesion-mask pre-annotation, editing it in three
planes, saving immutable revisions, and exporting a portable mask with provenance. The
default CPU workflow uses a deterministic demonstration provider; the optional GPU workflow
uses pinned DeepISLES. v1 is NIfTI-only and includes no telemetry.

## Research-use disclaimer

NeuroAnnotate is research software only. It is not a medical device and must not be used for
diagnosis, treatment, or clinical decision-making. The demonstration provider is not a trained
medical model. Review every artifact independently and follow the governance requirements that
apply to your data and research.

## Quick Start

Requirements: Docker with Compose and `make`.

```bash
git clone https://github.com/sifat371/neuroannotate.git
cd neuroannotate
cp .env.example .env
make demo-data
make seed-demo
docker compose up --build
```

Open the app at `http://localhost:5173` or the API documentation at
`http://localhost:8000/docs`. This default CPU/demo path downloads normal build dependencies,
not model weights. See the [demo walkthrough](docs/demo.md) and
[troubleshooting guide](docs/troubleshooting.md).

## GPU Quick Start

The optional provider is DeepISLES and requires an NVIDIA GPU, a compatible driver, NVIDIA
Container Toolkit, substantial disk space, and network access for a first-start model download.
Set `NEUROANNOTATE_INFERENCE_PROVIDER=deepisles` in `.env`, then run:

```bash
docker compose --profile gpu up
```

The profile adds a private-network DeepISLES service and a persistent model cache. It downloads
approximately 9.1 GB of weights on first start. This GPU path has not been executed on this host
because no licensed DWI/ADC/FLAIR validation triad was supplied. Follow [the GPU setup and
validation guide](docs/gpu.md), including its `make validate-gpu` procedure, before relying on
the integration in your own research environment.

## Workflow

1. Import exactly one DWI, ADC, and FLAIR NIfTI as an atomic case.
2. Queue a persisted CPU demo or optional DeepISLES inference job.
3. Review the DWI-native binary mask and edit it with brush/erase and undo/redo.
4. Save a complete immutable revision; unsaved edits remain visibly dirty.
5. Export only a saved, clean revision as `lesion-mask.nii.gz`, `provenance.json`, and a ZIP
   containing those two files.

See [workflow details](docs/workflow.md) and the [provenance contract](docs/provenance.md).

## Architecture

The React/Cornerstone3D frontend talks to a FastAPI service backed by SQLite metadata and local
NIfTI artifact storage. A provider boundary selects the deterministic CPU demo or the optional
private-network DeepISLES service; inference jobs are durable and asynchronous.

See [architecture details](docs/architecture.md).

## Testing and contributing

Run the complete local verification gate with:

```bash
make verify
```

The repository also provides `make test`, `make lint`, and `bash scripts/smoke.sh`. GPU
validation is separate because it requires suitable hardware, model weights, and a licensed
input triad. Development setup, focused commands, scope, and review expectations are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Citation

Release citation metadata is in [CITATION.cff](CITATION.cff). GitHub and compatible citation
tools can render it; update the version and release date for future releases. No claim of JOSS
eligibility is made. Eligibility must be checked against the then-current JOSS policy if a
submission is considered.

## License and third-party attribution

NeuroAnnotate is distributed under the [MIT License](LICENSE). The optional GPU image fetches
[`ezequieldlrosa/DeepIsles`](https://github.com/ezequieldlrosa/DeepIsles) at commit
`7658b608fc0d890cf14448ff3e58c47ad5c761e7`; that upstream project is Apache-2.0 licensed.
DeepISLES model weights are obtained separately from Zenodo and are never committed here.
Third-party packages and model artifacts remain subject to their own licenses and terms.
