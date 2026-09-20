from __future__ import annotations

import gzip
import math
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:  # Prefer the mature implementation when installed.
    import nibabel as nib  # type: ignore
except ImportError:  # Lightweight fallback keeps the demo/test path runnable offline.
    nib = None


# A compressed upload is not allowed to expand into an unbounded in-memory array.
# The loader works in float32 for source MRI data, so the working-set budget uses
# max(stored itemsize, 4) rather than only the on-disk datatype size.
MAX_NIFTI_VOXELS = 64 * 1024 * 1024
MAX_NIFTI_DECODED_BYTES = 256 * 1024 * 1024
MAX_NIFTI_VOX_OFFSET = 16 * 1024 * 1024

_NIFTI_DTYPES: dict[int, np.dtype] = {
    2: np.dtype(np.uint8),
    4: np.dtype(np.int16),
    8: np.dtype(np.int32),
    16: np.dtype(np.float32),
    64: np.dtype(np.float64),
    512: np.dtype(np.uint16),
}


@dataclass(frozen=True)
class Volume:
    data: np.ndarray
    affine: np.ndarray
    spacing: tuple[float, float, float]
    datatype: str
    spatial_units: str = "unknown"


@dataclass(frozen=True)
class NiftiHeaderInfo:
    shape: tuple[int, int, int]
    dtype: np.dtype
    offset: int
    endian: str


def _opener(path: Path, mode: str):
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, mode)
    return open(path, mode)


def _preflight_header(path: Path) -> NiftiHeaderInfo:
    """Inspect only the NIfTI-1 header and enforce decoded allocation budgets."""
    path = Path(path)
    with _opener(path, "rb") as stream:
        raw = stream.read(352)
    if len(raw) < 348:
        raise ValueError("not a supported NIfTI-1 file")

    if struct.unpack_from("<i", raw, 0)[0] == 348:
        endian = "<"
    elif struct.unpack_from(">i", raw, 0)[0] == 348:
        endian = ">"
    else:
        raise ValueError("not a supported NIfTI-1 file")

    dims = struct.unpack_from(f"{endian}8h", raw, 40)
    shape = tuple(int(value) for value in dims[1:4])
    if dims[0] != 3 or any(dimension <= 0 for dimension in shape):
        raise ValueError("expected a non-empty 3D NIfTI volume")

    datatype_code = int(struct.unpack_from(f"{endian}h", raw, 70)[0])
    dtype = _NIFTI_DTYPES.get(datatype_code)
    if dtype is None:
        raise ValueError(f"unsupported NIfTI datatype {datatype_code}")

    raw_offset = float(struct.unpack_from(f"{endian}f", raw, 108)[0])
    if not math.isfinite(raw_offset) or raw_offset < 0:
        raise ValueError("invalid NIfTI voxel offset")
    offset = max(352, int(round(raw_offset)))

    voxel_count = shape[0] * shape[1] * shape[2]
    working_bytes = voxel_count * max(dtype.itemsize, np.dtype(np.float32).itemsize)
    if (
        voxel_count > MAX_NIFTI_VOXELS
        or working_bytes > MAX_NIFTI_DECODED_BYTES
        or offset > MAX_NIFTI_VOX_OFFSET
    ):
        raise ValueError("decoded NIfTI budget exceeded")

    if not str(path).lower().endswith(".gz"):
        stored_bytes = voxel_count * dtype.itemsize
        if path.stat().st_size < offset + stored_bytes:
            raise ValueError("NIfTI payload is truncated")

    return NiftiHeaderInfo(shape=shape, dtype=dtype, offset=offset, endian=endian)


def load_volume(path: Path) -> Volume:
    path = Path(path)
    header_info = _preflight_header(path)
    if nib is not None:
        image = nib.load(str(path))
        if tuple(int(value) for value in image.shape) != header_info.shape:
            raise ValueError("NIfTI header geometry changed during load")
        return Volume(
            np.asarray(image.get_fdata(dtype=np.float32), dtype=np.float32),
            np.asarray(image.affine, dtype=float),
            tuple(float(v) for v in image.header.get_zooms()[:3]),
            str(np.dtype(image.header.get_data_dtype())),
            image.header.get_xyzt_units()[0],
        )

    count = header_info.shape[0] * header_info.shape[1] * header_info.shape[2]
    required_bytes = header_info.offset + count * header_info.dtype.itemsize
    with _opener(path, "rb") as fh:
        raw = fh.read(required_bytes)
    if len(raw) < 352:
        raise ValueError("not a supported NIfTI-1 file")

    endian = header_info.endian
    pixdim = struct.unpack_from(f"{endian}8f", raw, 76)
    arr = np.frombuffer(
        raw,
        dtype=header_info.dtype.newbyteorder(endian),
        count=count,
        offset=header_info.offset,
    )
    if arr.size != count:
        raise ValueError("NIfTI payload is truncated")

    arr = arr.reshape(header_info.shape, order="F").astype(np.float32, copy=False)
    slope = struct.unpack_from(f"{endian}f", raw, 112)[0]
    inter = struct.unpack_from(f"{endian}f", raw, 116)[0]
    if slope not in (0.0, 1.0):
        arr = arr * slope
    if inter != 0.0:
        arr = arr + inter

    sform_code = struct.unpack_from(f"{endian}h", raw, 254)[0]
    if sform_code:
        affine = np.eye(4, dtype=float)
        affine[0, :] = struct.unpack_from(f"{endian}4f", raw, 280)
        affine[1, :] = struct.unpack_from(f"{endian}4f", raw, 296)
        affine[2, :] = struct.unpack_from(f"{endian}4f", raw, 312)
    else:
        affine = np.diag(
            [
                pixdim[1] or 1.0,
                pixdim[2] or 1.0,
                pixdim[3] or 1.0,
                1.0,
            ]
        )

    units_code = raw[123] & 7
    return Volume(
        arr,
        affine,
        (float(pixdim[1]), float(pixdim[2]), float(pixdim[3])),
        str(header_info.dtype),
        {0: "unknown", 1: "meter", 2: "mm", 3: "micron"}.get(units_code, "unknown"),
    )


def save_volume(
    path: Path,
    data: np.ndarray,
    affine: np.ndarray,
    dtype=np.float32,
    spacing: tuple[float, float, float] | None = None,
    spatial_units: str = "mm",
) -> Path:
    path = Path(path)
    array = np.asarray(data, dtype=dtype)
    if array.ndim != 3:
        raise ValueError("only 3D NIfTI volumes are supported")

    affine = np.asarray(affine, dtype=float)
    if affine.shape != (4, 4) or not np.isfinite(affine).all():
        raise ValueError("invalid affine")
    stored_spacing = (
        tuple(float(value) for value in spacing)
        if spacing is not None
        else tuple(float(np.linalg.norm(affine[:3, axis])) or 1.0 for axis in range(3))
    )
    if len(stored_spacing) != 3 or any(
        not np.isfinite(value) or value <= 0 for value in stored_spacing
    ):
        raise ValueError("invalid voxel spacing")
    if spatial_units not in {"unknown", "meter", "mm", "micron"}:
        raise ValueError("unsupported NIfTI spatial units")

    if nib is not None:
        image = nib.Nifti1Image(array, affine)
        image.header.set_data_dtype(array.dtype)
        image.header.set_zooms(stored_spacing)
        image.header.set_xyzt_units(spatial_units)
        nib.save(image, str(path))
        return path

    datatype_map = {
        np.dtype(np.uint8): (2, 8),
        np.dtype(np.int16): (4, 16),
        np.dtype(np.int32): (8, 32),
        np.dtype(np.float32): (16, 32),
        np.dtype(np.float64): (64, 64),
        np.dtype(np.uint16): (512, 16),
    }
    data_type = array.dtype
    if data_type not in datatype_map:
        array = array.astype(np.float32)
        data_type = array.dtype
    datatype, bitpix = datatype_map[data_type]

    header = bytearray(352)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<8h", header, 40, 3, *array.shape, 1, 1, 1, 1)
    struct.pack_into("<h", header, 70, datatype)
    struct.pack_into("<h", header, 72, bitpix)
    struct.pack_into("<8f", header, 76, 1.0, *stored_spacing, 1.0, 0.0, 0.0, 0.0)
    struct.pack_into("<f", header, 108, 352.0)
    header[123] = {"unknown": 0, "meter": 1, "mm": 2, "micron": 3}[spatial_units]
    struct.pack_into("<h", header, 254, 1)  # sform_code
    struct.pack_into("<4f", header, 280, *affine[0, :].astype(float))
    struct.pack_into("<4f", header, 296, *affine[1, :].astype(float))
    struct.pack_into("<4f", header, 312, *affine[2, :].astype(float))
    header[344:348] = b"n+1\x00"

    payload = (
        array.astype(data_type.newbyteorder("<"), copy=False)
        .reshape(-1, order="F")
        .tobytes()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with _opener(path, "wb") as fh:
        fh.write(header)
        fh.write(payload)
    return path
