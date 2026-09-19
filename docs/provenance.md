# Export provenance

Every v1 export is an immutable snapshot of one saved annotation revision. Export creation
verifies the managed source triad, source segmentation, and revision artifacts before publishing
`lesion-mask.nii.gz` and `provenance.json`; the downloadable ZIP contains exactly those two
entries. The JSON is validated against
`backend/tests/fixtures/provenance_schema_v1.json` (`neuroannotate.provenance`, version `1.0`).

## Canonical geometry

The mask is binary `uint8` in DWI-native canonical geometry. Its shape, spacing, and affine come
from the case DWI. NeuroAnnotate does not register or resample during export.

## JSON sections

- `schema` and `schema_version` identify the committed provenance contract.
- `software` records application name/version and the Git commit when it can be resolved.
- `export` records the export ID and UTC creation timestamp.
- `case` records the portable case ID and `annotation_space: "DWI"`.
- `sources` has exactly `DWI`, `ADC`, and `FLAIR`. Each entry records artifact ID, SHA-256,
  shape, spacing, datatype, and affine.
- `ai_segmentation` records segmentation artifact/checksum, inference job, provider/model/service
  identity, job timestamps, provider configuration, and runtime metadata.
- `annotation` records revision ID, immediate parent, UTC timestamp, optional note, root-to-leaf
  lineage, and `edit_summary`.
- `output` fixes the filename to `lesion-mask.nii.gz` and records SHA-256, `uint8` datatype,
  binary label map, DWI shape, spacing, and affine.
- `disclaimer` states the research-only boundary.

## SHA-256 semantics

A SHA-256 identifies the exact bytes of a managed artifact, not an abstract image and not its
scientific validity.

- A source SHA-256 covers the immutable managed `.nii.gz` bytes. An uploaded `.nii.gz` is kept as
  uploaded; an uploaded uncompressed `.nii` is normalized to gzip first, so its digest covers the
  normalized managed artifact rather than the original upload bytes.
- `ai_segmentation.sha256` covers the validated persisted provider-output NIfTI bytes.
- A revision SHA-256, exposed by the revision API, covers that saved immutable revision NIfTI.
- `output.sha256` covers the exported `lesion-mask.nii.gz` bytes. Because export copies the saved
  revision, it must match the selected revision digest.

Checksums detect missing or changed bytes in this workflow. They are not signatures, identity
proof, performance scores, or clinical metrics.

## Portable exclusions and privacy

The provenance validator recursively rejects every `original_filename` field and every absolute
POSIX or Windows path value. Consequently, exports omit absolute host paths and original
filenames even though original filenames may exist in local case metadata. The schema also omits
the case display name. IDs, timestamps, optional revision notes, geometry, and provider runtime
metadata remain; inspect them under your research privacy policy before sharing an export.

## Edit summary semantics

`annotation.edit_summary` is computed against the immediate parent revision, or against the
source segmentation for a root revision:

- `added_voxels`: background-to-lesion voxel changes;
- `removed_voxels`: lesion-to-background voxel changes;
- `changed_voxels`: added plus removed voxels;
- `lesion_voxels`: foreground voxels in the saved revision; and
- `lesion_volume_ml`: foreground voxel count multiplied by DWI voxel volume, converted from mm³.

These are descriptive mask edit statistics. They are not clinical metrics, accuracy measures,
diagnostic measurements, treatment guidance, or evidence that a segmentation is correct.
