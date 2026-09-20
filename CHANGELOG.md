# Changelog

All notable changes to NeuroAnnotate are documented here.

## [1.0.0] - 2026-09-19

### Added

- Atomic DWI/ADC/FLAIR NIfTI case import and three-plane annotation workspace.
- Persisted asynchronous inference jobs with a deterministic CPU demonstration provider.
- Optional private-network DeepISLES GPU provider pinned to a reproducible upstream commit.
- Brush/erase editing, undo/redo, immutable revisions, and descriptive mask edit statistics.
- Portable DWI-native mask export with schema-validated provenance and a two-file ZIP bundle.
- Docker Compose development, smoke verification, CI, and release documentation.

### Research scope

- Single-user, local/self-hosted research software; NIfTI only.
- Not a medical device and not for diagnosis, treatment, or clinical decision-making.
