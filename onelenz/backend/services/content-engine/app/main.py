from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from shared.errors import AppError
from shared.errors.codes import INTERNAL_ERROR
from shared.logging import (
    RequestLoggingMiddleware,
    get_logger,
    setup_logging,
)

from .api.routes.asset import router as asset_router
from .api.routes.internal import router as internal_router
from .config import settings

setup_logging("content-engine")
logger = get_logger(__name__)

app = FastAPI(
    title="OneLenz Content Engine",
    description=(
        "Knowledge-hub ingestion, chunking, embedding, and"
        " signal matching"
    ),
    version="1.0.0",
)


@app.exception_handler(AppError)
async def app_error_handler(
    _request: Request, exc: AppError
):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
):
    messages = []
    for err in exc.errors():
        field = ".".join(
            str(loc)
            for loc in err["loc"]
            if loc != "body"
        )
        messages.append(
            f"{field}: {err['msg']}" if field else err["msg"]
        )
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "; ".join(messages),
            }
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(
    _request: Request, _exc: Exception
):
    logger.error("Unexpected error", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": INTERNAL_ERROR.code,
                "message": INTERNAL_ERROR.message,
            }
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    RequestLoggingMiddleware, service_name="content-engine"
)

app.include_router(
    asset_router, prefix="/content", tags=["content"]
)
app.include_router(
    internal_router, prefix="/content", tags=["internal"]
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "content-engine"}