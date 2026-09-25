# NeuroAnnotate

> **Development status:** active pre-release development. No stable version has been tagged yet.

NeuroAnnotate is a single-user, local/self-hosted research workspace for importing a hospital
brain-MRI DICOM ZIP or a curated DWI/ADC/FLAIR NIfTI triad, generating an ischemic-stroke
lesion pre-annotation, quantifying the candidate lesion, editing it in three planes, saving
immutable revisions, and exporting a portable mask with provenance. Hospital ZIP import
automatically identifies DWI, ADC, and FLAIR and converts only those series locally. The
default CPU workflow uses a deterministic demonstration provider; the optional GPU workflow
uses the maintained BrainLesion `stroke_segmentor` package (DeepISLES NVAUTO). No telemetry
is included.

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

The optional GPU provider uses DeepISLES NVAUTO through BrainLesion `stroke_segmentor`
0.0.3 and requires an NVIDIA GPU, a compatible driver, NVIDIA Container Toolkit, persistent
model storage, and network access for first-start weight download.
Set `NEUROANNOTATE_INFERENCE_PROVIDER=deepisles` in `.env`, then run:

```bash
docker compose --profile gpu up
```

The profile adds a private-network inference service and a persistent model cache. The current
container uses a Blackwell-capable PyTorch/CUDA build. This GPU path still requires an
end-to-end validation run on the actual deployment GPU and governed MRI data before a hospital
observer study. Follow [the GPU setup and validation guide](docs/gpu.md), including its
`make validate-gpu` procedure.

## Workflow

1. Import one hospital DICOM ZIP (auto-selecting DWI/ADC/FLAIR) or an explicit NIfTI triad.
2. Queue a persisted CPU demo or optional GPU stroke pre-segmentation job.
3. Review the DWI-native binary candidate mask and its lesion-volume measurement.
4. Correct the mask with brush/erase and undo/redo; saved revisions report corrected volume.
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

NeuroAnnotate is distributed under the [MIT License](LICENSE). The optional GPU service pins
BrainLesion `stroke-segmentor==0.0.3`, which exposes the DeepISLES NVAUTO algorithm and is
Apache-2.0 licensed upstream. Model weights are obtained separately at runtime and are never
committed here. Third-party packages and model artifacts remain subject to their own licenses
and terms.
