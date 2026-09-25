from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import nibabel as nib
import pydicom
from fastapi import UploadFile
from pydicom.errors import InvalidDicomError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import Case
from app.services.cases import import_case_triad
from app.services.storage import Storage

_MODALITIES = ("DWI", "ADC", "FLAIR")
_MAX_DICOM_FILES = 10_000


@dataclass
class DicomSeries:
    uid: str
    description: str = ""
    protocol: str = ""
    image_type: str = ""
    files: list[Path] = field(default_factory=list)

    @property
    def searchable(self) -> str:
        return " ".join((self.description, self.protocol, self.image_type)).upper()


def _safe_extract_zip(archive_path: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if not members:
                raise ApiError(422, "empty_dicom_archive", "The uploaded ZIP contains no files")
            if len(members) > _MAX_DICOM_FILES:
                raise ApiError(
                    413,
                    "too_many_dicom_files",
                    f"The uploaded ZIP contains more than {_MAX_DICOM_FILES} files",
                )

            expanded_limit = settings.max_upload_mb * 1024 * 1024 * 8
            if sum(member.file_size for member in members) > expanded_limit:
                raise ApiError(
                    413,
                    "dicom_archive_too_large",
                    "The expanded DICOM study exceeds the configured safety limit",
                )

            root = destination.resolve()
            for member in members:
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ApiError(
                        422,
                        "unsafe_dicom_archive",
                        "The uploaded ZIP contains an unsafe path",
                    )
                target = (destination / member_path).resolve()
                if root != target and root not in target.parents:
                    raise ApiError(
                        422,
                        "unsafe_dicom_archive",
                        "The uploaded ZIP contains an unsafe path",
                    )
            archive.extractall(destination)
    except zipfile.BadZipFile as exc:
        raise ApiError(422, "invalid_dicom_archive", "The uploaded file is not a valid ZIP") from exc


def _series_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\\".join(str(item) for item in value)
    return str(value)


def discover_mr_series(root: Path) -> list[DicomSeries]:
    grouped: dict[str, DicomSeries] = {}
    for path in root.rglob("*"):
        if not path.is_file() or path.name.upper() == "DICOMDIR":
            continue
        try:
            dataset = pydicom.dcmread(
                str(path),
                stop_before_pixels=True,
                force=True,
                specific_tags=[
                    "Modality",
                    "SeriesInstanceUID",
                    "SeriesDescription",
                    "ProtocolName",
                    "ImageType",
                ],
            )
        except (InvalidDicomError, OSError, ValueError):
            continue

        if _series_text(getattr(dataset, "Modality", "")).upper() != "MR":
            continue
        uid = _series_text(getattr(dataset, "SeriesInstanceUID", "")).strip()
        if not uid:
            continue

        series = grouped.get(uid)
        if series is None:
            series = DicomSeries(
                uid=uid,
                description=_series_text(getattr(dataset, "SeriesDescription", "")).strip(),
                protocol=_series_text(getattr(dataset, "ProtocolName", "")).strip(),
                image_type=_series_text(getattr(dataset, "ImageType", "")).strip(),
            )
            grouped[uid] = series
        series.files.append(path)

    return sorted(grouped.values(), key=lambda item: item.uid)


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(^|[^A-Z0-9]){re.escape(word)}([^A-Z0-9]|$)", text) is not None


def score_series(series: DicomSeries, modality: str) -> int:
    text = series.searchable
    if modality == "ADC":
        score = 0
        if _has_word(text, "ADC"):
            score += 20
        if "APPARENT DIFFUSION" in text:
            score += 16
        if "DIFFUSION" in text:
            score += 2
        if "TRACEW" in text or _has_word(text, "DWI"):
            score -= 8
        return score

    if modality == "DWI":
        score = 0
        if _has_word(text, "DWI"):
            score += 20
        if "TRACEW" in text:
            score += 16
        if "DIFFUSION" in text:
            score += 8
        if "B1000" in text or "B=1000" in text:
            score += 5
        if _has_word(text, "ADC") or "APPARENT DIFFUSION" in text:
            score -= 30
        return score

    if modality == "FLAIR":
        score = 0
        if _has_word(text, "FLAIR"):
            score += 24
        if "DARK-FLUID" in text or "DARK_FLUID" in text or "DARK FLUID" in text:
            score += 16
        if "TIRM" in text:
            score += 7
        if _has_word(text, "T2") or "T2_TSE" in text or "TSE" in text:
            score += 5
        if "_TRA" in text or " AX" in text or "AXIAL" in text:
            score += 2
        if _has_word(text, "T1") or text.startswith("T1_"):
            score -= 8
        if "DIFFUSION" in text or _has_word(text, "ADC"):
            score -= 20
        return score

    raise ValueError(f"Unsupported modality {modality}")


def select_required_series(series: list[DicomSeries]) -> dict[str, DicomSeries]:
    if not series:
        raise ApiError(422, "no_mr_series", "No MR image series were found in the uploaded study")

    selected: dict[str, DicomSeries] = {}
    thresholds = {"DWI": 10, "ADC": 10, "FLAIR": 10}

    for modality in _MODALITIES:
        ranked = sorted(
            ((score_series(candidate, modality), candidate) for candidate in series),
            key=lambda item: (item[0], len(item[1].files), item[1].uid),
            reverse=True,
        )
        best_score, best = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else -999
        if best_score < thresholds[modality]:
            raise ApiError(
                422,
                "missing_required_series",
                f"Could not confidently identify a {modality} series",
            )
        if second_score == best_score:
            raise ApiError(
                422,
                "ambiguous_required_series",
                f"Multiple MR series are equally likely to be {modality}; manual selection is required",
            )
        selected[modality] = best

    if len({item.uid for item in selected.values()}) != len(_MODALITIES):
        raise ApiError(
            422,
            "ambiguous_required_series",
            "The same MR series matched more than one required modality",
        )
    return selected


def _copy_series(series: DicomSeries, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(series.files):
        target = destination / f"{index:06d}.dcm"
        try:
            target.hardlink_to(source)
        except OSError:
            shutil.copy2(source, target)


def _convert_series(series: DicomSeries, modality: str, work_dir: Path) -> Path:
    series_dir = work_dir / "selected" / modality.lower()
    output_dir = work_dir / "converted" / modality.lower()
    _copy_series(series, series_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "dcm2niix",
        "-z",
        "y",
        "-b",
        "n",
        "-f",
        modality.lower(),
        "-o",
        str(output_dir),
        str(series_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
        )
    except FileNotFoundError as exc:
        raise ApiError(
            503,
            "dicom_converter_unavailable",
            "DICOM conversion is unavailable on this installation",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ApiError(504, "dicom_conversion_timeout", f"{modality} conversion timed out") from exc

    if completed.returncode != 0:
        raise ApiError(
            422,
            "dicom_conversion_failed",
            f"Could not convert the selected {modality} series",
        )

    outputs = sorted(output_dir.glob("*.nii.gz"))
    if len(outputs) != 1:
        raise ApiError(
            422,
            "dicom_conversion_ambiguous",
            f"{modality} conversion produced {len(outputs)} NIfTI volumes; manual series selection is required",
        )
    return outputs[0]


def _scrub_nifti_header(path: Path) -> None:
    image = nib.load(str(path))
    header = image.header.copy()
    for field_name in ("descrip", "aux_file", "intent_name"):
        if field_name in header:
            header[field_name] = b""
    nib.save(nib.Nifti1Image(image.dataobj, image.affine, header), str(path))


def _stage_archive(upload: UploadFile, destination: Path) -> None:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    total = 0
    upload.file.seek(0)
    with destination.open("wb") as output:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ApiError(
                    413,
                    "file_too_large",
                    "Uploaded DICOM ZIP exceeds the configured size limit",
                )
            output.write(chunk)


def import_dicom_zip(
    session: Session,
    storage: Storage,
    name: str,
    upload: UploadFile,
) -> Case:
    filename = (upload.filename or "").lower()
    if filename and not filename.endswith(".zip"):
        raise ApiError(422, "invalid_dicom_archive", "Hospital DICOM import expects one .zip file")

    storage.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dicom-import-", dir=storage.root) as temporary:
        work_dir = Path(temporary)
        archive_path = work_dir / "study.zip"
        extracted_dir = work_dir / "dicom"
        extracted_dir.mkdir()
        _stage_archive(upload, archive_path)
        _safe_extract_zip(archive_path, extracted_dir)

        series = discover_mr_series(extracted_dir)
        selected = select_required_series(series)
        converted = {
            modality: _convert_series(selected[modality], modality, work_dir)
            for modality in _MODALITIES
        }
        for path in converted.values():
            _scrub_nifti_header(path)

        handles = {modality: path.open("rb") for modality, path in converted.items()}
        try:
            uploads = {
                modality: StarletteUploadFile(
                    filename=f"{modality.lower()}.nii.gz",
                    file=handles[modality],
                )
                for modality in _MODALITIES
            }
            return import_case_triad(session, storage, name, uploads)
        finally:
            for handle in handles.values():
                handle.close()
