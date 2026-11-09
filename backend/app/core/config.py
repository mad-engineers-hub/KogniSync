from pydantic import model_validator
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

    # Google Maps / Routes API Configuration (Pluggable Cloud Provider)
    GOOGLE_ROUTES_ENABLED: bool = False
    GOOGLE_MAPS_API_KEY: str | None = None

    # Valhalla OpenStreetMap Routing Configuration (Self-Hosted Engine)
    VALHALLA_ENABLED: bool = True
    VALHALLA_BASE_URL: str = "http://localhost:8002"
    VALHALLA_TIMEOUT_SECONDS: float = 5.0
    VALHALLA_ALLOW_LOCALHOST: bool = False

    # TomTom Orbis Traffic API v2 Configuration (Real Road Incidents - Milestone M3.8)
    TOMTOM_API_KEY: str | None = None
    TRAFFIC_INCIDENT_API_KEY: str | None = None  # Backwards-compatible alias
    TOMTOM_TRAFFIC_ENABLED: bool = True
    TOMTOM_BASE_URL: str = "https://api.tomtom.com/maps/orbis/traffic/incidents/details"
    TOMTOM_TIMEOUT_SECONDS: float = 3.0
    TOMTOM_CONNECT_TIMEOUT_SECONDS: float = 1.5
    TOMTOM_MAX_RETRIES: int = 2
    TOMTOM_MAX_REQUESTS_PER_ASSESSMENT: int = 5

    # GTFS Realtime Configuration (Milestone M3.8)
    GTFS_REALTIME_ENABLED: bool = False
    GTFS_REALTIME_FEED_URL: str | None = None
    GTFS_REALTIME_API_KEY: str | None = None
    GTFS_REALTIME_TIMEOUT_SECONDS: float = 5.0

    # Data Freshness Thresholds (seconds) (Milestone M3.8)
    FRESHNESS_ROAD_INCIDENT_SECONDS: int = 1800       # 30 min fresh threshold
    FRESHNESS_SERVICE_ALERT_SECONDS: int = 3600       # 60 min fresh threshold
    FRESHNESS_TRIP_UPDATE_SECONDS: int = 300          # 5 min fresh threshold
    FRESHNESS_VEHICLE_POSITION_SECONDS: int = 60      # 1 min fresh threshold

    @model_validator(mode="after")
    def validate_provider_configurations(self) -> "Settings":
        # Synchronize TOMTOM_API_KEY and legacy TRAFFIC_INCIDENT_API_KEY alias
        if not self.TOMTOM_API_KEY and self.TRAFFIC_INCIDENT_API_KEY:
            self.TOMTOM_API_KEY = self.TRAFFIC_INCIDENT_API_KEY
        elif self.TOMTOM_API_KEY and not self.TRAFFIC_INCIDENT_API_KEY:
            self.TRAFFIC_INCIDENT_API_KEY = self.TOMTOM_API_KEY

        # Valhalla localhost safeguard
        is_localhost = any(
            h in (self.VALHALLA_BASE_URL or "").lower()
            for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1")
        )
        if self.ENVIRONMENT == "production" and is_localhost:
            if not self.VALHALLA_ALLOW_LOCALHOST:
                self.VALHALLA_ENABLED = False
        return self

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
