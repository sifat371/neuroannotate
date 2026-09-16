import numpy as np

from app.scripts.generate_demo_data import generate_demo_case
from app.services.nifti_codec import load_volume


def test_demo_data_is_deterministic(tmp_path):
    first = generate_demo_case(tmp_path / "a")
    second = generate_demo_case(tmp_path / "b")
    for modality in ("DWI", "ADC", "FLAIR"):
        first_volume = load_volume(first[modality])
        second_volume = load_volume(second[modality])
        np.testing.assert_array_equal(first_volume.data, second_volume.data)
        np.testing.assert_allclose(first_volume.affine, second_volume.affine)
        assert first_volume.data.shape == (64, 64, 48)
