from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: str = "change-this-local-key"
    database_url: str = "sqlite:///./doc_audit.db"
    redis_url: str = "redis://localhost:6379/0"
    upload_dir: str = "./data/uploads"
    processed_dir: str = "./data/processed"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=20, gt=0)
    audit_tolerance: str = "0.05"
    min_field_confidence: float = Field(default=60, ge=0, le=100)
    save_preprocessed: bool = False
    retention_days: int = Field(default=90, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
