from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NeuroAnnotate"
    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./neuroannotate.db"
    inference_provider: str = "demo"
    deepisles_url: str | None = None
    max_upload_mb: int = Field(default=512, ge=1, le=2048)
    frontend_origin: str = "http://localhost:5173"
    sample_data_dir: Path = Path("../sample_data")
    model_config = SettingsConfigDict(env_prefix="NEUROANNOTATE_", env_file=".env")


settings = Settings()
