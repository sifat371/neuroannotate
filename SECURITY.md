# Security and privacy

## Supported development state

NeuroAnnotate is currently under active pre-release development and has no tagged stable release.
Security fixes target the current `main` branch until the first versioned release is published.
Older development snapshots may not receive fixes.

## Deployment boundary

NeuroAnnotate v1 is single-user, local/self-hosted research software. It has no authentication or
authorization layer and must not be exposed directly to an untrusted network. Restrict access at
the host/network boundary and protect the configured data directory and backups. The application
does not include telemetry.

Uploaded NIfTI files are untrusted input. The backend bounds upload size and validates readable,
non-empty 3D numeric volumes with finite geometry before persistence. Imports are staged and
rolled back on failure. These checks reduce risk but are not a security guarantee; keep the
application and dependencies patched and process sensitive data only under appropriate approval.

The optional DeepISLES service has no published host port in the supplied Compose configuration
and is reachable by the backend on the private Compose network. Do not add a public port without
an explicit threat review. Model weights are downloaded into a named volume and checked against
the documented MD5 before extraction.

Portable exports contain a mask and provenance. Provenance validation recursively rejects
absolute path values and `original_filename` fields, so host paths and original filenames are
omitted. Case/revision identifiers and optional notes remain in provenance and may still be
sensitive; inspect exports before sharing.

## Reporting a vulnerability

Use the repository's private GitHub security-advisory reporting path:
`https://github.com/sifat371/neuroannotate/security/advisories/new`. Include affected version,
reproduction steps, impact, and a suggested mitigation if known. If private reporting is not
available, open a minimal public issue requesting a private contact route and omit exploit,
participant, and host details. Please allow maintainers time to investigate before disclosure.
This process does not imply a guaranteed response time, embargo, or security certification.
