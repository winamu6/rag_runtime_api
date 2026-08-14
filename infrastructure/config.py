from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/rag_runtime"

    MODEL_REGISTRY_POLL_SECONDS: int = 10
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0

    LOG_LEVEL: str = "INFO"

    CORS_ALLOW_ORIGINS: str = "*"

    @property
    def cors_allow_origins_list(self) -> list[str]:
        raw = self.CORS_ALLOW_ORIGINS.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()