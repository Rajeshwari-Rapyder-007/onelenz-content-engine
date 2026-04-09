from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Auth-service configuration. Values loaded from environment variables."""

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

    # JWT (RS256) — PEM content from AWS Secrets Manager
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_access_token_expire_minutes: int = 2
    jwt_refresh_token_expire_minutes: int = 15

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Logging
    log_level: str = "DEBUG"

    # Auth
    lockout_threshold: int = 3
    lockout_duration_minutes: int = 30

    # Email
    email_provider: str = "mock"
    aws_ses_from_email: str = "noreply@onelenz.ai"
    aws_ses_region: str = "ap-south-1"

    # OTP
    otp_expiry_minutes: int = 10

    model_config = {"env_file": "../../../.env", "extra": "ignore"}


settings = Settings()
