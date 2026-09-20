from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    AnnotationRevision,
    Case,
    InferenceJob,
    SegmentationArtifact,
    SourceArtifact,
)


class CaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, name: str) -> Case:
        case = Case(name=name)
        self.session.add(case)
        self.session.commit()
        self.session.refresh(case)
        return case

    def add_imported_case(
        self,
        case: Case,
        artifacts: list[SourceArtifact],
    ) -> Case:
        """Persist a case and its source triad in one transaction."""
        case.source_artifacts.extend(artifacts)
        self.session.add(case)
        self.session.commit()
        return case

    def list(self) -> list[Case]:
        stmt = (
            select(Case)
            .options(selectinload(Case.source_artifacts))
            .order_by(Case.created_at)
        )
        return list(self.session.scalars(stmt).all())

    def get(self, case_id: str) -> Case | None:
        stmt = (
            select(Case)
            .where(Case.id == case_id)
            .options(selectinload(Case.source_artifacts))
        )
        return self.session.scalar(stmt)

    def get_by_name(self, name: str) -> Case | None:
        return self.session.scalar(select(Case).where(Case.name == name))

    def get_modality(self, case_id: str, modality: str) -> SourceArtifact | None:
        stmt = select(SourceArtifact).where(
            SourceArtifact.case_id == case_id, SourceArtifact.modality == modality
        )
        return self.session.scalar(stmt)

    def add_modality(self, artifact: SourceArtifact) -> SourceArtifact:
        self.session.add(artifact)
        self.session.commit()
        self.session.refresh(artifact)
        return artifact

    def add_inference(
        self,
        job: InferenceJob,
        segmentation: SegmentationArtifact,
    ) -> InferenceJob:
        self.session.add_all((job, segmentation))
        self.session.commit()
        self.session.refresh(job)
        return job

    def latest_inference(self, case_id: str) -> InferenceJob | None:
        stmt = (
            select(InferenceJob)
            .where(InferenceJob.case_id == case_id)
            .options(selectinload(InferenceJob.segmentation))
            .order_by(InferenceJob.created_at.desc())
        )
        return self.session.scalar(stmt)

    def get_inference(self, run_id: str) -> InferenceJob | None:
        stmt = (
            select(InferenceJob)
            .where(InferenceJob.id == run_id)
            .options(selectinload(InferenceJob.segmentation))
        )
        return self.session.scalar(stmt)

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
