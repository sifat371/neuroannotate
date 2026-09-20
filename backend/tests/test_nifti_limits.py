import gzip
import struct

import nibabel as nib
import numpy as np
import pytest

from app.core.errors import ApiError
from app.services import nifti_codec
from app.services.nifti import inspect_nifti


@pytest.mark.parametrize('fallback', [False, True])
@pytest.mark.parametrize(('shape', 'datatype', 'offset'), [
    ((1024, 1024, 1024), np.uint8, 352),
    ((512, 512, 256), np.float64, 352),
    ((2, 2, 2), np.uint8, 2**30),
])
def test_huge_compressed_declaration_rejected_before_voxel_read(
    tmp_path, monkeypatch, fallback, shape, datatype, offset,
):
    header = nib.Nifti1Header()
    header.set_data_shape(shape)
    header.set_data_dtype(datatype)
    header['vox_offset'] = offset
    path = tmp_path / 'tiny.nii.gz'
    with gzip.open(path, 'wb') as stream:
        stream.write(header.binaryblock + bytes(4))
    assert path.stat().st_size < 512
    if fallback:
        monkeypatch.setattr(nifti_codec, 'nib', None)
    else:
        def forbidden_materialization(*args, **kwargs):
            raise AssertionError('voxel allocation attempted before budget check')
        monkeypatch.setattr(nib.Nifti1Image, 'get_fdata', forbidden_materialization)
    with pytest.raises(ApiError, match='decoded NIfTI budget') as error:
        inspect_nifti(path)
    assert error.value.status_code == 422


@pytest.mark.parametrize('extension', ['.nii', '.nii.gz'])
@pytest.mark.parametrize('fallback', [False, True])
def test_bounded_reader_retains_valid_values(tmp_path, monkeypatch, extension, fallback):
    path = tmp_path / f'valid{extension}'
    data = np.arange(24, dtype=np.int16).reshape((2, 3, 4))
    nifti_codec.save_volume(path, data, np.eye(4), dtype=np.int16)
    if fallback:
        monkeypatch.setattr(nifti_codec, 'nib', None)
    np.testing.assert_array_equal(nifti_codec.load_volume(path).data, data)


def test_invalid_dimension_rejected_before_allocation(tmp_path):
    path = tmp_path / 'invalid.nii'
    header = bytearray(nib.Nifti1Header().binaryblock + bytes(4))
    struct.pack_into('<8h', header, 40, 3, -1, 4, 4, 1, 1, 1, 1)
    path.write_bytes(header)
    with pytest.raises(ApiError, match='non-empty 3D'):
        inspect_nifti(path)


def test_fallback_reader_never_materializes_unbounded_trailing_payload(tmp_path, monkeypatch):
    import io

    path = tmp_path / 'bounded.nii'
    nifti_codec.save_volume(
        path,
        np.arange(8, dtype=np.int16).reshape((2, 2, 2)),
        np.eye(4),
        dtype=np.int16,
    )
    raw = path.read_bytes() + (b'\x00' * 4096)

    class BoundedReader(io.BytesIO):
        def read(self, size=-1):
            if size is None or size < 0:
                raise AssertionError('fallback reader attempted an unbounded decompression read')
            return super().read(size)

    monkeypatch.setattr(nifti_codec, 'nib', None)
    monkeypatch.setattr(nifti_codec, '_opener', lambda *_args, **_kwargs: BoundedReader(raw))

    volume = nifti_codec.load_volume(path)
    assert volume.data.shape == (2, 2, 2)
    np.testing.assert_array_equal(volume.data, np.arange(8, dtype=np.int16).reshape((2, 2, 2)))
