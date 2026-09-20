import json
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

RELEASE_VERSION = "1.0.0"
REPOSITORY_CODE = "https://github.com/sifat371/neuroannotate"


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_cff_metadata(cff: str) -> Mapping[str, object]:
    try:
        document = yaml.safe_load(cff)
    except yaml.YAMLError as exc:
        raise AssertionError("CITATION.cff must be valid YAML/CFF") from exc
    assert isinstance(document, Mapping), "CITATION.cff must be a top-level mapping"
    return document


def _assert_cff_release_identity(document: Mapping[str, object]) -> None:
    assert document.get("title") == "NeuroAnnotate"
    assert document.get("version") == RELEASE_VERSION
    assert document.get("repository-code") == REPOSITORY_CODE


def test_release_metadata_files_exist(repo_root: Path) -> None:
    for rel in [
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "CITATION.cff",
        "SECURITY.md",
        "AI_USAGE.md",
        "docs/gpu.md",
        "docs/workflow.md",
        "docs/provenance.md",
        "docs/troubleshooting.md",
    ]:
        assert (repo_root / rel).is_file(), rel

    _assert_cff_release_identity(
        _load_cff_metadata((repo_root / "CITATION.cff").read_text(encoding="utf-8"))
    )


@pytest.mark.parametrize(
    ("cff", "message"),
    [
        ("title: [NeuroAnnotate\n", "valid YAML/CFF"),
        ("- title: NeuroAnnotate\n", "top-level mapping"),
    ],
)
def test_cff_metadata_requires_valid_top_level_mapping(cff: str, message: str) -> None:
    with pytest.raises(AssertionError, match=message):
        _load_cff_metadata(cff)


def test_cff_metadata_requires_exact_scalar_release_identity() -> None:
    with pytest.raises(AssertionError):
        _assert_cff_release_identity(
            {
                "title": "NeuroAnnotate",
                "version": RELEASE_VERSION,
                "repository-code": [REPOSITORY_CODE],
            }
        )


def test_release_identity_surfaces_match_citation_metadata(repo_root: Path, client) -> None:
    from app.services.exports import _software_identity
    from app.services.inference.demo import DemoSegmentationProvider
    from app.services.inference.nnunet import NNUNetProvider

    backend_metadata = tomllib.loads(
        (repo_root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )
    frontend_metadata = json.loads(
        (repo_root / "frontend" / "package.json").read_text(encoding="utf-8")
    )

    assert backend_metadata["project"]["version"] == RELEASE_VERSION
    assert frontend_metadata["version"] == RELEASE_VERSION
    assert client.get("/openapi.json").json()["info"]["version"] == RELEASE_VERSION
    assert _software_identity()["version"] == RELEASE_VERSION
    assert DemoSegmentationProvider().info().service_version == RELEASE_VERSION
    assert NNUNetProvider().info().service_version == RELEASE_VERSION


def test_readme_links_to_release_documentation(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    required_links = {
        "CONTRIBUTING.md",
        "CITATION.cff",
        "LICENSE",
        "docs/architecture.md",
        "docs/gpu.md",
        "docs/workflow.md",
        "docs/provenance.md",
        "docs/troubleshooting.md",
    }

    linked_paths = set(re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", readme))
    assert required_links <= linked_paths
    for rel in linked_paths:
        if "://" not in rel:
            assert (repo_root / rel).exists(), f"broken README link: {rel}"


def test_research_scope_and_gpu_release_facts_are_documented(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    gpu = (repo_root / "docs/gpu.md").read_text(encoding="utf-8")
    provenance = (repo_root / "docs/provenance.md").read_text(encoding="utf-8")

    assert "not a medical device" in readme.lower()
    assert "docker compose --profile gpu up" in readme
    assert "DeepISLES" in readme
    assert "7658b608fc0d890cf14448ff3e58c47ad5c761e7" in gpu
    assert "14026715" in gpu
    assert "stroke_ensemble_weights.7z" in gpu
    assert "be5b6dfcd66b55c2e6dc6db9a5880f7f" in gpu
    assert "make validate-gpu" in gpu
    assert "DWI-native" in provenance
    assert "SHA-256" in provenance
    assert "original filenames" in provenance
    assert "absolute" in provenance


def test_export_docs_distinguish_portable_snapshot_from_raw_compatibility_download(
    repo_root: Path,
) -> None:
    workflow = (repo_root / "docs/workflow.md").read_text(encoding="utf-8")
    provenance = (repo_root / "docs/provenance.md").read_text(encoding="utf-8")
    combined = f"{workflow}\n{provenance}"

    assert "POST `/api/cases/{case_id}/exports`" in combined
    assert "`/api/exports/{export_id}/mask`" in combined
    assert "`/api/exports/{export_id}/provenance`" in combined
    assert "`/api/exports/{export_id}/bundle`" in combined
    assert "GET `/api/cases/{case_id}/export?revision_id=...`" in combined
    assert "raw saved revision NIfTI" in combined
    assert "not a portable provenance bundle" in combined
