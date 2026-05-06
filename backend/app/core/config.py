"""Application configuration loaded from environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # App
    APP_NAME: str = "AI Document & Multimedia Q&A"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/aiqa"

    # JWT
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_TRANSCRIPTION_MODEL: str = "whisper-1"

    # Storage
    UPLOAD_DIR: str = "/app/storage/uploads"
    CHROMA_DIR: str = "/app/storage/chroma"
    MAX_UPLOAD_SIZE_MB: int = 100

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Redis (cache + rate-limit). Empty REDIS_URL disables both gracefully.
    REDIS_URL: str = "redis://redis:6379/0"
    EMBEDDING_CACHE_TTL: int = 60 * 60 * 24  # 24 hours
    RATE_LIMIT_ASK_PER_MINUTE: int = 30
    RATE_LIMIT_UPLOAD_PER_MINUTE: int = 10

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


settings = get_settings()
