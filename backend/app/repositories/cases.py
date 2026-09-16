from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import AnnotationRevision, Case, InferenceRun, ModalityArtifact


class CaseRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, name: str) -> Case:
        case = Case(name=name)
        self.session.add(case)
        self.session.commit()
        self.session.refresh(case)
        return case

    def list(self) -> list[Case]:
        stmt = select(Case).options(selectinload(Case.modalities)).order_by(Case.created_at)
        return list(self.session.scalars(stmt).all())

    def get(self, case_id: str) -> Case | None:
        stmt = select(Case).where(Case.id == case_id).options(selectinload(Case.modalities))
        return self.session.scalar(stmt)

    def get_by_name(self, name: str) -> Case | None:
        return self.session.scalar(select(Case).where(Case.name == name))

    def get_modality(self, case_id: str, modality: str) -> ModalityArtifact | None:
        stmt = select(ModalityArtifact).where(
            ModalityArtifact.case_id == case_id, ModalityArtifact.modality == modality
        )
        return self.session.scalar(stmt)

    def add_modality(self, artifact: ModalityArtifact) -> ModalityArtifact:
        self.session.add(artifact)
        self.session.commit()
        self.session.refresh(artifact)
        return artifact

    def add_inference(self, run: InferenceRun) -> InferenceRun:
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def latest_inference(self, case_id: str) -> InferenceRun | None:
        stmt = (
            select(InferenceRun)
            .where(InferenceRun.case_id == case_id)
            .order_by(InferenceRun.created_at.desc())
        )
        return self.session.scalar(stmt)

    def get_inference(self, run_id: str) -> InferenceRun | None:
        return self.session.get(InferenceRun, run_id)

    def add_revision(self, revision: AnnotationRevision) -> AnnotationRevision:
        self.session.add(revision)
        self.session.commit()
        self.session.refresh(revision)
        return revision

    def list_revisions(self, case_id: str) -> list[AnnotationRevision]:
        stmt = (
            select(AnnotationRevision)
            .where(AnnotationRevision.case_id == case_id)
            .order_by(AnnotationRevision.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_revision(self, revision_id: str) -> AnnotationRevision | None:
        return self.session.get(AnnotationRevision, revision_id)
