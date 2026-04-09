import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .context import RequestContext, clear_request_context, set_request_context
from .logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that sets request context for logging and logs request/response summary."""

    def __init__(self, app, service_name: str = ""):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.perf_counter()

        # Set context for this request — all logs within will include these fields
        ctx = RequestContext(
            request_id=request_id,
            endpoint=request.url.path,
            method=request.method,
            service_name=self.service_name,
        )
        set_request_context(ctx)

        # Add request_id to response headers for client-side tracing
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            response.headers["X-Request-ID"] = request_id

            logger.info(
                "Request completed",
                extra={
                    "x_status_code": response.status_code,
                    "x_duration_ms": duration_ms,
                },
            )

            return response
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "Request failed",
                extra={"x_duration_ms": duration_ms},
                exc_info=True,
            )
            raise
        finally:
            clear_request_context()
