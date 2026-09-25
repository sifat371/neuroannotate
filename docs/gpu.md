# Optional stroke-segmentation GPU provider

The default `docker compose up` remains the CPU-only deterministic demo and does not download
model weights. The `gpu` profile adds a private inference service that uses BrainLesion
`stroke_segmentor==0.0.3`, a maintained package exposing the DeepISLES NVAUTO ischemic-stroke
segmentation model.

This integration is research software only. It produces an AI candidate lesion mask for expert
review/correction and is not a diagnostic endpoint.

## Pinned runtime

- Implementation: BrainLesion `stroke_segmentor==0.0.3`
- Model family: DeepISLES NVAUTO
- Package license: Apache-2.0 upstream
- Required model inputs: DWI and ADC
- NeuroAnnotate case inputs: DWI, ADC, and FLAIR; FLAIR remains available for expert review
- Weight source used by the package: Zenodo record `16920681`
- GPU runtime: PyTorch `2.7.1` CUDA `12.8`

PyTorch 2.7 is the first stable release line with NVIDIA Blackwell support. The model still has
to pass `make validate-gpu` on the exact deployment host before it is used in a hospital
observer study.

## Host prerequisites

1. NVIDIA GPU and a host driver compatible with the container's CUDA-enabled PyTorch runtime.
2. Docker Engine with Compose v2.
3. NVIDIA Container Toolkit configured for Docker.
4. Network access to package registries while building and to Zenodo on the first model run.
5. Persistent disk space for Docker layers and the model checkpoint cache.

Verify Docker sees the GPU before starting NeuroAnnotate.

## Start the GPU profile

Set the backend provider in `.env`:

```dotenv
NEUROANNOTATE_INFERENCE_PROVIDER=deepisles
NEUROANNOTATE_DEEPISLES_URL=http://deepisles:8080
```

The historical provider key `deepisles` is retained for API compatibility. Runtime provenance
records the exact maintained implementation and version.

Start the stack:

```bash
docker compose --profile gpu up --build
```

The `deepisles-model-cache` named volume is mounted at `/models`. The runner redirects the
`stroke_segmentor` checkpoint cache to `/models/weights`, so weights downloaded on the first
inference survive container rebuilds. Once cached, an installation can reuse those weights
without downloading them again.

The backend reports GPU readiness at `http://localhost:8000/api/health`. GPU mode is considered
ready only when CUDA is available and the private service reports the pinned package identity.

## End-to-end validation

`make validate-gpu` remains intentionally separate from CI because it requires a real GPU and
governed MRI data. Supply a directory containing:

```text
dwi.nii.gz
adc.nii.gz
flair.nii.gz
```

Then run:

```bash
NEUROANNOTATE_GPU_TEST_CASE=/absolute/path/to/licensed-triad make validate-gpu
```

The validator creates an isolated Compose project, imports the triad, runs the GPU model, checks
that the result is finite binary `uint8` data in DWI geometry, saves a revision, and validates
the exported mask/bundle/provenance contract. A successful run on the deployment GPU is required
evidence for that environment.

## Hospital DICOM pilot

The application can also accept one hospital DICOM ZIP from the UI. Import happens in the
backend before inference:

```text
DICOM ZIP
  -> safe temporary extraction
  -> MR series discovery
  -> DWI / ADC / FLAIR selection
  -> dcm2niix conversion
  -> NIfTI header scrub
  -> immutable NeuroAnnotate case
  -> GPU pre-segmentation
  -> expert review / correction
```

The raw DICOM extraction directory is temporary and is deleted after conversion. For a hospital
study, use pseudonymous research case names and follow the institution's ethics, access-control,
retention, and de-identification requirements.

## Common failures

- **GPU service unavailable:** verify the `gpu` profile is active, the backend provider is
  `deepisles`, `nvidia-smi` works on the host, and NVIDIA Container Toolkit is configured.
- **Model cannot initialize:** inspect `docker compose --profile gpu logs deepisles`; on first
  inference also verify Zenodo connectivity and free disk space.
- **DICOM import cannot identify a required series:** NeuroAnnotate deliberately refuses
  ambiguous series selection. Use the NIfTI triad import as a fallback until manual DICOM series
  selection is added.
- **DICOM conversion produces multiple volumes:** use an explicitly curated NIfTI triad for that
  study and retain the case as a compatibility finding for the importer.
- **Inference output is rejected:** the returned mask must be binary `uint8` and match DWI
  shape/affine.
- **Validation rejects the triad:** make sure all three exact lowercase filenames exist and are
  readable.

See [troubleshooting.md](troubleshooting.md) for CPU and full-stack checks.
