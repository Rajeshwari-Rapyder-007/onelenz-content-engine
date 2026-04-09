from datetime import datetime

from pydantic import BaseModel, HttpUrl


# ── Request Models ──────────────────────────────────────────────────


class UrlSubmitRequest(BaseModel):
    url: HttpUrl
    category_id: str | None = None
    entity_id: str | None = None  # Only for internal KH-0 calls


class AssetUpdateRequest(BaseModel):
    category_id: str | None = None
    file_name: str | None = None


# ── Response Models ─────────────────────────────────────────────────


class AssetResponse(BaseModel):
    asset_id: str
    file_name: str
    category_id: str | None = None
    source_type: str
    status: str
    chunk_count: int | None = None
    page_count: int | None = None
    credits_consumed: float | None = None
    created_on: datetime


class AssetCreateResponse(BaseModel):
    assets: list[AssetResponse]


class UrlCreateResponse(BaseModel):
    asset_id: str
    url: str
    source_type: str
    status: str


class AssetDetailResponse(BaseModel):
    asset_id: str
    file_name: str
    category_id: str | None = None
    source_type: str
    status: str
    file_size_bytes: int | None = None
    page_count: int | None = None
    chunk_count: int | None = None
    credits_consumed: float | None = None
    error_message: str | None = None
    created_on: datetime
    modified_on: datetime | None = None


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    page: int
    page_size: int


# ── Stats Models ────────────────────────────────────────────────────


class CategoryStats(BaseModel):
    category_id: str
    asset_count: int
    chunk_count: int


class StatusStats(BaseModel):
    status: str
    count: int


class StatsResponse(BaseModel):
    total_assets: int
    total_chunks: int
    total_storage_bytes: int
    by_category: list[CategoryStats]
    by_status: list[StatusStats]


# ── Error Models ────────────────────────────────────────────────────


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
