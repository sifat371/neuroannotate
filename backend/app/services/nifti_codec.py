from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:  # Prefer the mature implementation when installed.
    import nibabel as nib  # type: ignore
except ImportError:  # Lightweight fallback keeps the demo/test path runnable offline.
    nib = None


@dataclass(frozen=True)
class Volume:
    data: np.ndarray
    affine: np.ndarray
    spacing: tuple[float, float, float]


def _opener(path: Path, mode: str):
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, mode)
    return open(path, mode)


def load_volume(path: Path) -> Volume:
    path = Path(path)
    if nib is not None:
        image = nib.load(str(path))
        if len(image.shape) != 3:
            raise ValueError("expected a 3D NIfTI volume")
        return Volume(
            np.asarray(image.get_fdata(), dtype=np.float32),
            np.asarray(image.affine, dtype=float),
            tuple(float(v) for v in image.header.get_zooms()[:3]),
        )

    with _opener(path, "rb") as fh:
        raw = fh.read()
    if len(raw) < 352 or struct.unpack_from("<i", raw, 0)[0] != 348:
        raise ValueError("not a supported NIfTI-1 file")

    dims = struct.unpack_from("<8h", raw, 40)
    if dims[0] != 3:
        raise ValueError("expected a 3D NIfTI-1 volume")
    shape = tuple(int(v) for v in dims[1:4])

    datatype = struct.unpack_from("<h", raw, 70)[0]
    dtype_map = {
        2: np.uint8,
        4: np.int16,
        8: np.int32,
        16: np.float32,
        64: np.float64,
        512: np.uint16,
    }
    if datatype not in dtype_map:
        raise ValueError(f"unsupported NIfTI datatype {datatype}")

    pixdim = struct.unpack_from("<8f", raw, 76)
    offset = max(352, int(round(struct.unpack_from("<f", raw, 108)[0])))
    count = int(np.prod(shape))
    arr = np.frombuffer(
        raw,
        dtype=np.dtype(dtype_map[datatype]).newbyteorder("<"),
        count=count,
        offset=offset,
    )
    if arr.size != count:
        raise ValueError("NIfTI payload is truncated")

    arr = arr.reshape(shape, order="F").astype(np.float32, copy=False)
    slope = struct.unpack_from("<f", raw, 112)[0]
    inter = struct.unpack_from("<f", raw, 116)[0]
    if slope not in (0.0, 1.0):
        arr = arr * slope
    if inter != 0.0:
        arr = arr + inter

    sform_code = struct.unpack_from("<h", raw, 254)[0]
    if sform_code:
        affine = np.eye(4, dtype=float)
        affine[0, :] = struct.unpack_from("<4f", raw, 280)
        affine[1, :] = struct.unpack_from("<4f", raw, 296)
        affine[2, :] = struct.unpack_from("<4f", raw, 312)
    else:
        affine = np.diag(
            [
                pixdim[1] or 1.0,
                pixdim[2] or 1.0,
                pixdim[3] or 1.0,
                1.0,
            ]
        )

    return Volume(
        arr,
        affine,
        (float(pixdim[1]), float(pixdim[2]), float(pixdim[3])),
    )


def save_volume(
    path: Path,
    data: np.ndarray,
    affine: np.ndarray,
    dtype=np.float32,
) -> Path:
    path = Path(path)
    array = np.asarray(data, dtype=dtype)
    if array.ndim != 3:
        raise ValueError("only 3D NIfTI volumes are supported")

    affine = np.asarray(affine, dtype=float)
    if affine.shape != (4, 4) or not np.isfinite(affine).all():
        raise ValueError("invalid affine")

    if nib is not None:
        image = nib.Nifti1Image(array, affine)
        image.header.set_data_dtype(array.dtype)
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
    spacing = [float(np.linalg.norm(affine[:3, i])) or 1.0 for i in range(3)]
    struct.pack_into("<8f", header, 76, 1.0, *spacing, 1.0, 0.0, 0.0, 0.0)
    struct.pack_into("<f", header, 108, 352.0)
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
