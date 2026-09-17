import uuid
from pathlib import Path


class Storage:
    """Resolve managed artifact paths beneath one configured data root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def staging_dir(self, import_id: str) -> Path:
        """Create and return a private directory for an in-progress import."""
        path = self.root / ".staging" / import_id
        path.mkdir(parents=True, exist_ok=False)
        return path

    def case_dir(self, case_id: str) -> Path:
        path = self.root / "cases" / case_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def source_dir(self, case_id: str) -> Path:
        """Create and return a case's immutable source directory."""
        path = self.case_dir(case_id) / "source"
        path.mkdir(parents=True, exist_ok=False)
        return path

    def source_path(self, case_id: str, modality: str) -> Path:
        """Return the fixed managed path for a source modality."""
        return self.root / "cases" / case_id / "source" / f"{modality.lower()}.nii.gz"

    def modality_path(self, case_id: str, modality: str, compressed: bool) -> Path:
        suffix = ".nii.gz" if compressed else ".nii"
        path = self.case_dir(case_id) / "modalities" / f"{modality.lower()}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def inference_path(self, case_id: str) -> Path:
        path = self.case_dir(case_id) / "inference" / f"{uuid.uuid4()}.nii.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def revision_path(self, case_id: str) -> Path:
        path = self.case_dir(case_id) / "revisions" / f"{uuid.uuid4()}.nii.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def resolve(self, relative_path: str) -> Path:
        return self.root / relative_path
