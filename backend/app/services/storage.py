import uuid
from pathlib import Path


class Storage:
    def __init__(self, root: Path):
        self.root = Path(root)

    def case_dir(self, case_id: str) -> Path:
        path = self.root / "cases" / case_id
        path.mkdir(parents=True, exist_ok=True)
        return path

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
