# Optional DeepISLES GPU provider

The v1 optional real-model provider is DeepISLES. The default `docker compose up` remains the
CPU-only deterministic demo and does not download model weights. The GPU profile adds a
DeepISLES service on the private Compose network; it does not publish that service's port to the
host.

This integration is research software only. It is not for diagnosis, treatment, or clinical
decision-making. The GPU path has not been executed on this host because no licensed
DWI/ADC/FLAIR validation triad was supplied.

## Pinned inputs

- Upstream: [`ezequieldlrosa/DeepIsles`](https://github.com/ezequieldlrosa/DeepIsles)
- Upstream license: Apache-2.0
- Commit: `7658b608fc0d890cf14448ff3e58c47ad5c761e7`
- Weights: Zenodo record `14026715`, file `stroke_ensemble_weights.7z`
- Expected MD5: `be5b6dfcd66b55c2e6dc6db9a5880f7f`
- Download size: approximately 9.1 GB; allow additional space for extraction and images

Weights are downloaded at startup and are never committed to this repository. Confirm that the
upstream license, weight terms, and intended research use are acceptable in your environment.

The committed runner uses these DeepISLES settings:

```text
skull_strip=False
fast=False
save_team_outputs=False
results_mni=False
parallelize=True
```

`results_mni=False` keeps the returned segmentation in native DWI geometry. The service and
backend independently reject a result that is not finite binary `uint8` data matching the DWI
shape and affine.

## Host prerequisites

1. An NVIDIA GPU supported by the pinned CUDA 11.3 runtime and a compatible host driver.
2. Docker Engine with Compose v2.
3. [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
   installed and configured for Docker.
4. Network access to GitHub/package registries while building and to Zenodo on first start.
5. Enough persistent storage for the approximately 9.1 GB archive, extracted weights, Docker
   layers, and temporary download/extraction files.

Verify Docker can expose the GPU before starting NeuroAnnotate, using an NVIDIA CUDA image
compatible with your driver according to NVIDIA's toolkit documentation.

## Start the GPU profile

Set the backend provider in `.env`:

```dotenv
NEUROANNOTATE_INFERENCE_PROVIDER=deepisles
NEUROANNOTATE_DEEPISLES_URL=http://deepisles:8080
```

Then build and start all services:

```bash
docker compose --profile gpu up
```

Add `--build` when you need to rebuild the local images after source changes.

The `deepisles-model-cache` named volume is mounted at `/models`. On the first start,
`fetch_weights.sh` downloads to a temporary file, checks the exact MD5, extracts to a temporary
directory, publishes `/models/weights`, and writes a readiness marker. The archive itself is not
retained. Later starts reuse the weights only when both the marker and weights directory exist.
An interrupted or corrupt download leaves no readiness marker, and the next start retries the
download and integrity check.

The backend reports GPU readiness at `http://localhost:8000/api/health`. It accepts DeepISLES as
ready only when the service responds with the pinned commit, reports CUDA available, and reports
itself ready.

## End-to-end validation

`make validate-gpu` is intentionally separate from CI and the CPU smoke test. Supply a directory
containing a licensed triad with these exact names:

```text
dwi.nii.gz
adc.nii.gz
flair.nii.gz
```

Run:

```bash
NEUROANNOTATE_GPU_TEST_CASE=/absolute/path/to/licensed-triad make validate-gpu
```

The validator uses a temporary Compose project and temporary host data directory, waits for
validated CUDA/service readiness, imports the triad, runs DeepISLES, saves a revision, and checks
the exported mask/bundle/provenance contract. It has a 30-minute bound and removes the temporary
project and data afterward; the named model cache persists. Do not use unlicensed or
inappropriately governed data. A successful run in your environment is required evidence for
that environment; this repository does not claim that validation has passed on this host.

## Common failures

- **Service remains unavailable:** confirm the `gpu` profile is active, the backend provider is
  `deepisles`, and `docker compose --profile gpu logs deepisles` shows a running service. The
  model endpoint is private by design; inspect it from within the Compose network.
- **CUDA unavailable or no device reserved:** verify `nvidia-smi` on the host, NVIDIA Container
  Toolkit configuration, Docker daemon restart after toolkit setup, driver/runtime
  compatibility, and the Compose GPU reservation. CPU fallback is not accepted in GPU mode.
- **Weight download fails:** check Zenodo connectivity, free space, DNS/proxy settings, and the
  DeepISLES logs. Startup retries transport failures; a checksum mismatch stops startup rather
  than using the archive.
- **Weights repeatedly download:** inspect the `deepisles-model-cache` volume for both
  `/models/weights` and `/models/.neuroannotate-weights-ready`. Do not hand-create the marker.
- **Inference job fails:** inspect the persisted failure category/message and service logs. A
  retry creates a new job; it does not rewrite the failed attempt. Confirm all three source files
  are readable NIfTI and that the returned mask matches DWI geometry.
- **Validation rejects the triad:** use an existing directory with all three exact lowercase
  filenames and ensure the caller has permission to read them.

See [troubleshooting.md](troubleshooting.md) for CPU and full-stack checks.
