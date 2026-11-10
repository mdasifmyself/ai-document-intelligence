"""All settings come from environment variables (see .env.example). Nothing secret is hard-coded."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DocIntel"
    version: str = "1.0.0"

    database_url: str = "postgresql+psycopg://docintel:docintel@db:5432/docintel"
    redis_url: str = "redis://redis:6379/0"
    storage_dir: str = "/data/uploads"
    samples_dir: str = "/data/samples"

    # AI provider: "n8n" (gateway webhook that holds the OpenAI key), "openai" (direct), or "fake" (tests)
    ai_provider: str = "n8n"
    ai_gateway_url: str = ""
    ai_gateway_key: str = ""
    openai_api_key: str = ""
    extraction_model: str = "gpt-4.1-mini"
    vision_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    ai_concurrency: int = 4
    ai_timeout_s: int = 120
    ai_daily_call_limit: int = 3000
    ai_cache: bool = True               # reuse AI answers for identical text: resumable jobs, no repeated cost

    # Access and limits
    access_codes: str = ""            # comma-separated; empty = open (local development only)
    cors_origins: str = "http://localhost:3000"
    max_file_mb: int = 50
    max_files_per_upload: int = 50
    max_pages: int = 1500
    uploads_per_minute: int = 60

    # OCR
    ocr_dpi: int = 300
    ocr_lang: str = "eng"
    ocr_low_confidence: float = 60.0  # below this mean word confidence, the vision fallback is tried
    vision_fallback: bool = True

    # Recovery
    recovery_stale_minutes: int = 15

    # Validation
    amount_tolerance_abs: float = 0.02
    amount_tolerance_rel: float = 0.0   # no percentage slack: a wrong total on a large invoice must still be caught
    amount_tolerance_per_line: float = 0.005

    @property
    def access_code_list(self) -> list[str]:
        return [c.strip() for c in self.access_codes.split(",") if c.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [c.strip() for c in self.cors_origins.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
