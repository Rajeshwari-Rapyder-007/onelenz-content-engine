from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Content engine service configuration."""

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/onelenz"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    environment: str = "dev"

    # Logging
    log_level: str = "INFO"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # JWT (public key only — verifies, doesn't sign)
    jwt_public_key: str = ""

    # S3
    s3_bucket_content: str = "onelenz-content-engine"
    aws_region: str = "ap-south-1"

    # Celery (Redis DB 2)
    celery_broker_url: str = "redis://localhost:6379/2"

    # Bedrock (Titan V2)
    bedrock_embedding_model_id: str = (
        "amazon.titan-embed-text-v2:0"
    )
    bedrock_embedding_dimensions: int = 1024
    bedrock_max_batch_size: int = 25

    # Docling extraction
    docling_max_num_pages: int = 200
    docling_max_file_size: int = 52_428_800  # 50MB
    docling_enable_ocr: bool = False

    # Chunking (Docling HybridChunker)
    chunk_max_tokens: int = 512

    # Crawling (Crawl4AI)
    crawl_max_depth: int = 1
    crawl_max_pages: int = 50
    crawl_include_external: bool = False
    crawl_timeout_seconds: int = 120
    crawl_listing_link_threshold: int = 5
    crawl_content_filter_threshold: float = 0.6

    # Ingestion
    max_file_size_bytes: int = 52_428_800
    max_files_per_upload: int = 20
    max_assets_per_day_per_entity: int = 100
    ingestion_task_retries: int = 3
    allowed_file_types: str = "pdf,docx,pptx,xlsx,txt,zip"
    max_zip_decompressed_bytes: int = 209_715_200
    max_files_per_zip: int = 50

    # Credits
    credits_per_page: float = 0.5

    # Signal matching (app-level for v1)
    match_result_limit: int = 3
    match_result_max: int = 5
    similarity_threshold: float = 0.65

    # Internal service auth (for KH-0 signup trigger)
    internal_service_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()