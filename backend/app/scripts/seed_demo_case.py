import json
from pathlib import Path

from app.core.config import settings
from app.db.models import ModalityArtifact
from app.db.session import init_db, new_session
from app.repositories.cases import CaseRepository
from app.scripts.generate_demo_data import generate_demo_case
from app.services.nifti import inspect_nifti
from app.services.storage import Storage


def seed_demo_case() -> str:
    init_db()
    generated = generate_demo_case(Path(settings.sample_data_dir))
    storage = Storage(settings.data_dir)

    with new_session() as session:
        repo = CaseRepository(session)
        existing = repo.get_by_name("NeuroAnnotate Demo")
        if existing:
            return existing.id

        case = repo.create("NeuroAnnotate Demo")
        for modality, src in generated.items():
            dst = storage.modality_path(case.id, modality, True)
            dst.write_bytes(src.read_bytes())
            meta = inspect_nifti(dst)
            repo.add_modality(
                ModalityArtifact(
                    case_id=case.id,
                    modality=modality,
                    relative_path=storage.relative(dst),
                    shape_x=meta.shape[0],
                    shape_y=meta.shape[1],
                    shape_z=meta.shape[2],
                    spacing_x=meta.spacing[0],
                    spacing_y=meta.spacing[1],
                    spacing_z=meta.spacing[2],
                    affine_json=json.dumps(meta.affine.tolist()),
                )
            )
        return case.id


if __name__ == "__main__":
    print(seed_demo_case())
