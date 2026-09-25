from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.schemas.cases import CaseDetail, CaseRead
from app.services.cases import case_to_detail, case_to_dict, import_case_triad, require_case
from app.services.dicom_import import import_dicom_zip
from app.services.storage import Storage

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("", response_model=list[CaseRead])
def list_cases(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    return [case_to_dict(case) for case in CaseRepository(session).list()]


@router.post("", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
def create_case(
    name: Annotated[str, Form(min_length=1, max_length=200)],
    dwi: Annotated[UploadFile, File()],
    adc: Annotated[UploadFile, File()],
    flair: Annotated[UploadFile, File()],
    session: Session = Depends(get_session),
) -> CaseDetail:
    case = import_case_triad(
        session,
        Storage(settings.data_dir),
        name,
        {"DWI": dwi, "ADC": adc, "FLAIR": flair},
    )
    return CaseDetail.model_validate(case_to_detail(case))


@router.post("/dicom", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
def create_case_from_dicom(
    name: Annotated[str, Form(min_length=1, max_length=200)],
    study: Annotated[UploadFile, File()],
    session: Session = Depends(get_session),
) -> CaseDetail:
    """Import a hospital DICOM study ZIP and auto-select DWI/ADC/FLAIR."""
    case = import_dicom_zip(
        session,
        Storage(settings.data_dir),
        name,
        study,
    )
    return CaseDetail.model_validate(case_to_detail(case))


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(
    case_id: str,
    session: Session = Depends(get_session),
) -> CaseDetail:
    return CaseDetail.model_validate(case_to_detail(require_case(CaseRepository(session), case_id)))
