from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "KogniSync"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Internal Security & Operational API Key
    INTERNAL_API_KEY: str | None = None

    # JWT Authentication Configuration
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str | None = None
    JWT_AUDIENCE: str | None = None
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Database Configuration
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5434
    POSTGRES_USER: str = "kognisync"
    POSTGRES_PASSWORD: str = "kognisync_pass"
    POSTGRES_DB: str = "kognisync_db"
    DATABASE_URL: str = "postgresql+asyncpg://kognisync:kognisync_pass@localhost:5434/kognisync_db"

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6380
    REDIS_URL: str = "redis://localhost:6380/0"

    # Gemini AI Configuration
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "models/gemini-3.5-flash-lite"

    # Google Maps / Routes API Configuration (Pluggable)
    GOOGLE_ROUTES_ENABLED: bool = False
    GOOGLE_MAPS_API_KEY: str | None = None

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
