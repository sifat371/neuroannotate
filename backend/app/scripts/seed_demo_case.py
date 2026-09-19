from contextlib import ExitStack
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.db.session import init_db, new_session
from app.repositories.cases import CaseRepository
from app.scripts.generate_demo_data import generate_demo_case
from app.services.cases import import_case_triad
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

        with ExitStack() as stack:
            uploads = {
                modality: UploadFile(
                    filename=generated[modality].name,
                    file=stack.enter_context(generated[modality].open("rb")),
                )
                for modality in ("DWI", "ADC", "FLAIR")
            }
            case = import_case_triad(
                session,
                storage,
                "NeuroAnnotate Demo",
                uploads,
            )
        return case.id


if __name__ == "__main__":
    print(seed_demo_case())
