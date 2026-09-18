import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings


@pytest.mark.parametrize("value", ["0", "-1", "2049", "999999999"])
def test_max_upload_mb_rejects_values_outside_operational_range(monkeypatch, value):
    monkeypatch.setenv("NEUROANNOTATE_MAX_UPLOAD_MB", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["1", "512", "2048"])
def test_max_upload_mb_accepts_values_within_operational_range(monkeypatch, value):
    monkeypatch.setenv("NEUROANNOTATE_MAX_UPLOAD_MB", value)

    assert Settings(_env_file=None).max_upload_mb == int(value)


def test_max_upload_mb_default_is_512_mebibytes():
    assert Settings(_env_file=None).max_upload_mb == 512


def test_environment_override_does_not_mutate_shared_settings(monkeypatch):
    original_max_upload_mb = settings.max_upload_mb
    monkeypatch.setenv("NEUROANNOTATE_MAX_UPLOAD_MB", "1")

    assert Settings(_env_file=None).max_upload_mb == 1
    assert settings.max_upload_mb == original_max_upload_mb
