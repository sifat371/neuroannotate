from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.schemas.cases import CaseCreate, CaseRead
from app.services.cases import case_to_dict, require_case

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("", response_model=list[CaseRead])
def list_cases(session: Session = Depends(get_session)):
    return [case_to_dict(case) for case in CaseRepository(session).list()]


@router.post("", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate, session: Session = Depends(get_session)):
    return case_to_dict(CaseRepository(session).create(payload.name))


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: str, session: Session = Depends(get_session)):
    return case_to_dict(require_case(CaseRepository(session), case_id))
