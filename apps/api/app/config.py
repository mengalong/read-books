from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "回卷"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origin: str = "http://localhost:3000"

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data/app.db'}"
    upload_dir: Path = PROJECT_ROOT / "data/uploads"
    parsed_dir: Path = PROJECT_ROOT / "data/parsed"
    seed_demo_data: bool = True
    ocr_enabled: bool = True
    ocr_command: str = "swift"
    ocr_script: Path = PROJECT_ROOT / "scripts/pdf_ocr.swift"

    mock_mode: bool = True
    llm_base_url: str | None = None
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_model: str | None = None
    llm_timeout_ms: int = 60_000
    llm_temperature: float = 0.2

    @model_validator(mode="after")
    def resolve_local_paths(self) -> "Settings":
        if self.database_url.startswith("sqlite:///./"):
            relative_path = self.database_url.removeprefix("sqlite:///./")
            self.database_url = f"sqlite:///{PROJECT_ROOT / relative_path}"
        if not self.upload_dir.is_absolute():
            self.upload_dir = PROJECT_ROOT / self.upload_dir
        if not self.parsed_dir.is_absolute():
            self.parsed_dir = PROJECT_ROOT / self.parsed_dir
        if not self.ocr_script.is_absolute():
            self.ocr_script = PROJECT_ROOT / self.ocr_script
        return self

    def ensure_directories(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
