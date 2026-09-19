import re
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _top_level_cff_value(cff: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*['\"]?([^'\"\n]+)['\"]?\s*$", cff, re.MULTILINE)
    assert match is not None, f"missing {key!r} in CITATION.cff"
    return match.group(1).strip()


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

    cff = (repo_root / "CITATION.cff").read_text(encoding="utf-8")
    assert _top_level_cff_value(cff, "title") == "NeuroAnnotate"
    assert _top_level_cff_value(cff, "version") == "1.0.0"
    assert (
        _top_level_cff_value(cff, "repository-code")
        == "https://github.com/sifat371/neuroannotate"
    )


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
