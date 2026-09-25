"""HTTP adapter for the isolated DeepISLES GPU service."""

import json
import math
import os
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.inference.base import (
    CaseInput,
    ProviderInfo,
    ProviderOutputPersistenceError,
    ProviderResult,
    ProviderRuntimeError,
    ProviderUnavailableError,
)

_MEMBERS = ("segmentation.nii.gz", "metadata.json")
_MAX_METADATA_BYTES = 1024 * 1024
_RESPONSE_OVERHEAD_BYTES = 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_ALLOWED_COMPRESSION = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)


class DeepISLESProvider:
    """Submit immutable source bytes to the private DeepISLES service."""

    name = "deepisles"
    requires_async = True

    def __init__(self, service_url: str | None = None) -> None:
        self.service_url = service_url.rstrip("/") if service_url else None

    def info(self) -> ProviderInfo:
        """Return configured identity without issuing a network request."""
        return ProviderInfo(
            self.name,
            "DeepISLES NVAUTO via BrainLesion stroke_segmentor",
            "stroke-segmentor-0.0.3",
            "1.1.0",
            self.service_url is not None,
        )

    def segment(self, case: CaseInput, output_path: Path) -> ProviderResult:
        """POST the exact modality triad and persist a validated service result."""
        if self.service_url is None:
            raise ProviderUnavailableError("DeepISLES service URL is not configured")
        try:
            with self._multipart(case) as files, httpx.Client(timeout=None) as client:
                with client.stream(
                    "POST", self.service_url + "/v1/segment", files=files
                ) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        raise ProviderRuntimeError("DeepISLES service returned an error")
                    content = self._read_response(response)
        except httpx.TransportError as exc:
            raise ProviderUnavailableError("DeepISLES service is unavailable") from exc
        mask_bytes, metadata = self._parse_archive(content)
        self._atomic_write(Path(output_path), mask_bytes)
        return ProviderResult(
            mask_path=Path(output_path),
            provider=metadata["provider"],
            model_name=metadata["model_name"],
            model_version=metadata["model_version"],
            service_version=metadata["service_version"],
            configuration=metadata["configuration"],
            runtime=metadata["runtime"],
        )

    @contextmanager
    def _multipart(self, case: CaseInput) -> Iterator[dict[str, Any]]:
        """Open exactly the required files for the duration of the HTTP request."""
        try:
            with ExitStack() as stack:
                files = {
                    name.lower(): (
                        path.name,
                        stack.enter_context(path.open("rb")),
                        "application/gzip",
                    )
                    for name, path in (
                        ("DWI", case.modality_paths["DWI"]),
                        ("ADC", case.modality_paths["ADC"]),
                        ("FLAIR", case.modality_paths["FLAIR"]),
                    )
                }
                yield files
        except (KeyError, OSError) as exc:
            raise ProviderRuntimeError("DeepISLES input files are unavailable") from exc

    @staticmethod
    def _response_limit() -> int:
        """Bound provider bytes from the configured upload budget plus ZIP overhead."""
        return settings.max_upload_mb * 1024 * 1024 + _RESPONSE_OVERHEAD_BYTES

    @classmethod
    def _read_response(cls, response: httpx.Response) -> bytes:
        """Read a streaming HTTP response without exceeding the configured cap."""
        limit = cls._response_limit()
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit or int(content_length) < 0:
                    raise ValueError("response is too large")
            except ValueError as exc:
                raise ProviderRuntimeError("DeepISLES response size is invalid") from exc
        chunks = []
        received = 0
        try:
            for chunk in response.iter_bytes():
                received += len(chunk)
                if received > limit:
                    raise ProviderRuntimeError("DeepISLES response is too large")
                chunks.append(chunk)
        except httpx.TransportError as exc:
            raise ProviderUnavailableError("DeepISLES service is unavailable") from exc
        return b"".join(chunks)

    @classmethod
    def _parse_archive(cls, content: bytes) -> tuple[bytes, dict[str, Any]]:
        """Validate an exact safe ZIP without extracting untrusted members."""
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if (
                    len(infos) != 2
                    or len(set(names)) != 2
                    or set(names) != set(_MEMBERS)
                    or any(
                        info.is_dir()
                        or "/" in info.filename
                        or "\\" in info.filename
                        for info in infos
                    )
                ):
                    raise ValueError("archive members are invalid")
                info_by_name = {info.filename: info for info in infos}
                segmentation_limit = settings.max_upload_mb * 1024 * 1024
                cls._validate_member(info_by_name["metadata.json"], _MAX_METADATA_BYTES)
                cls._validate_member(
                    info_by_name["segmentation.nii.gz"], segmentation_limit
                )
                metadata_raw = cls._read_member(
                    archive, info_by_name["metadata.json"], _MAX_METADATA_BYTES
                )
                metadata = json.loads(metadata_raw)
                if not isinstance(metadata, dict):
                    raise ValueError("metadata is not an object")
                cls._validate_metadata(metadata)
                return (
                    cls._read_member(
                        archive, info_by_name["segmentation.nii.gz"], segmentation_limit
                    ),
                    metadata,
                )
        except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            raise ProviderRuntimeError("DeepISLES response archive is invalid") from exc

    @staticmethod
    def _validate_member(info: zipfile.ZipInfo, limit: int) -> None:
        """Reject dangerous declared ZIP member properties before decompression."""
        if (
            info.file_size < 0
            or info.compress_size < 0
            or info.file_size > limit
            or info.compress_size > limit
            or info.flag_bits & 0x1
            or info.compress_type not in _ALLOWED_COMPRESSION
        ):
            raise ValueError("archive member is unsafe")
        ratio = info.file_size / max(info.compress_size, 1)
        if ratio > _MAX_COMPRESSION_RATIO:
            raise ValueError("archive member compression ratio is unsafe")

    @staticmethod
    def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
        """Read one prevalidated member with an independent decompression cap."""
        chunks = []
        received = 0
        with archive.open(info) as member:
            while True:
                chunk = member.read(min(64 * 1024, limit + 1 - received))
                if not chunk:
                    break
                received += len(chunk)
                if received > limit:
                    raise ValueError("archive member exceeds its limit")
                chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _validate_metadata(metadata: dict[str, Any]) -> None:
        """Require the identifying, configuration, and runtime provenance contract."""
        string_fields = (
            "provider",
            "service",
            "service_version",
            "model_name",
            "model_version",
            "upstream_commit",
        )
        if any(
            not isinstance(metadata.get(field), str) or not metadata[field]
            for field in string_fields
        ):
            raise ValueError("metadata identity is invalid")
        if metadata["provider"] != "deepisles":
            raise ValueError("metadata provider is invalid")
        if (
            metadata["service_version"] != "1.1.0"
            or metadata["model_version"] != "stroke-segmentor-0.0.3"
            or metadata["upstream_commit"] != "BrainLesion/stroke_segmentor@0.0.3"
        ):
            raise ValueError("metadata model identity is invalid")
        if not isinstance(metadata.get("configuration"), dict) or not isinstance(
            metadata.get("runtime"), dict
        ):
            raise ValueError("metadata configuration or runtime is invalid")
        configuration = metadata["configuration"]
        if (
            configuration.get("implementation") != "BrainLesion stroke_segmentor"
            or configuration.get("modalities") != ["ADC", "DWI"]
            or configuration.get("flair_used") is not False
        ):
            raise ValueError("metadata configuration is invalid")
        duration = metadata["runtime"].get("duration_seconds")
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not math.isfinite(duration)
            or duration < 0
        ):
            raise ValueError("metadata duration is invalid")
        if not isinstance(metadata["runtime"].get("device"), str):
            raise ValueError("metadata device is invalid")
        if not isinstance(metadata["runtime"].get("cuda_available"), bool):
            raise ValueError("metadata CUDA availability is invalid")

    @staticmethod
    def _atomic_write(output_path: Path, contents: bytes) -> None:
        """Publish bytes with a same-filesystem atomic replace or typed failure."""
        temporary_name = None
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".segmentation-", suffix=".tmp", dir=str(output_path.parent)
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, output_path)
            temporary_name = None
        except OSError as exc:
            raise ProviderOutputPersistenceError("Could not persist DeepISLES output") from exc
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
