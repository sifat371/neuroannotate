from app.core.errors import ApiError
from app.db.models import Case

REQUIRED_MODALITIES = {"DWI", "ADC", "FLAIR"}


def is_ready_for_inference(modalities: set[str]) -> bool:
    return modalities == REQUIRED_MODALITIES


def case_to_dict(case: Case) -> dict:
    modalities = sorted(m.modality for m in case.modalities)
    return {
        "id": case.id,
        "name": case.name,
        "created_at": case.created_at,
        "modalities": modalities,
        "ready_for_inference": is_ready_for_inference(set(modalities)),
    }


def require_case(repo, case_id: str) -> Case:
    case = repo.get(case_id)
    if not case:
        raise ApiError(404, "case_not_found", "Case not found")
    return case
