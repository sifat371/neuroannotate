import json

import nibabel as nib
import numpy as np
import pytest

from app.services import nifti_codec


@pytest.mark.parametrize(('units', 'spacing', 'expected_ml'), [
    ('mm', (2, 3, 4), 0.192),
    ('meter', (.002, .003, .004), 0.192),
    ('micron', (2000, 3000, 4000), 0.192),
    ('unknown', (2, 3, 4), None),
])
def test_demo_revision_export_preserves_units(client, tmp_path, units, spacing, expected_ml):
    path = tmp_path / 'source.nii.gz'
    source = nib.Nifti1Image(np.ones((2, 2, 2), dtype=np.float32), np.eye(4))
    source.header.set_zooms(spacing)
    source.header.set_xyzt_units(units)
    nib.save(source, path)
    response = client.post('/api/cases', data={'name': 'units'}, files={
        name: ('source.nii.gz', path.read_bytes(), 'application/gzip')
        for name in ('dwi', 'adc', 'flair')
    })
    assert response.status_code == 201, response.text
    case_id = response.json()['id']
    job = client.post(f'/api/cases/{case_id}/segment').json()
    mask = client.get(f"/api/segmentations/{job['id']}/file.nii.gz")
    mask_path = tmp_path / 'mask.nii.gz'
    mask_path.write_bytes(mask.content)
    generated = nib.load(mask_path)
    assert generated.header.get_xyzt_units()[0] == units
    assert generated.header.get_zooms() == pytest.approx(spacing)
    np.testing.assert_allclose(generated.affine, np.eye(4))
    revision = client.post(f'/api/cases/{case_id}/revisions', files={
        'voxels': ('mask.bin', bytes([1] * 8), 'application/octet-stream'),
    }, data={'shape': json.dumps([2, 2, 2]), 'source_segmentation_id': job['id']})
    if expected_ml is None:
        assert revision.status_code == 422
        assert revision.json()['error']['code'] == 'unsupported_spatial_units'
        return
    assert revision.status_code == 201, revision.text
    assert revision.json()['edit_stats']['lesion_volume_ml'] == pytest.approx(expected_ml)
    exported = client.post(
        f'/api/cases/{case_id}/exports',
        json={'revision_id': revision.json()['id']},
    )
    assert exported.status_code == 201, exported.text
    mask_path.write_bytes(client.get(f"/api/exports/{exported.json()['id']}/mask").content)
    saved = nib.load(mask_path)
    assert saved.header.get_xyzt_units()[0] == units
    assert saved.header.get_zooms() == pytest.approx(spacing)
    np.testing.assert_allclose(saved.affine, np.eye(4))


@pytest.mark.parametrize('fallback', [False, True])
@pytest.mark.parametrize('units', ['mm', 'meter', 'micron', 'unknown'])
def test_codec_spatial_unit_round_trip(tmp_path, monkeypatch, fallback, units):
    if fallback:
        monkeypatch.setattr(nifti_codec, 'nib', None)
    path = tmp_path / 'mask.nii.gz'
    nifti_codec.save_volume(path, np.ones((2, 2, 2)), np.eye(4), spatial_units=units)
    assert nifti_codec.load_volume(path).spatial_units == units
    assert nib.load(path).header.get_xyzt_units()[0] == units
