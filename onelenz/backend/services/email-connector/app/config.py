from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Email connector service configuration."""

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/onelenz"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    environment: str = "dev"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Logging
    log_level: str = "DEBUG"

    # Microsoft OAuth
    ms_oauth_client_id: str = ""
    ms_oauth_client_secret: str = ""
    ms_graph_base_url: str = "https://graph.microsoft.com/v1.0"

    # Token encryption
    token_encryption_key: str = ""

    # S3
    s3_bucket_emails: str = "onelenz-emails"
    aws_region: str = "ap-south-1"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"

    # Sync
    sync_frequency_minutes: int = 15
    token_refresh_buffer_minutes: int = 5
    initial_fetch_days: int = 30
    max_fetch_days: int = 90

    # Frontend
    frontend_url: str = "http://localhost:3000"

    @property
    def ms_oauth_redirect_uri(self) -> str:
        """Derived from frontend_url — must match Azure app registration."""
        return f"{self.frontend_url}/settings/integrations/callback"

    model_config = {"env_file": "../../../.env", "extra": "ignore"}


settings = Settings()
