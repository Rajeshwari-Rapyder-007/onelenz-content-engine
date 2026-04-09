import contextvars
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestContext:
    """Holds per-request context that gets attached to every log line."""

    request_id: str = ""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    endpoint: str = ""
    method: str = ""
    service_name: str = ""


# ContextVar ensures each async request gets its own isolated context
_request_context: contextvars.ContextVar[RequestContext] = contextvars.ContextVar(
    "request_context", default=RequestContext()
)


def request_context() -> RequestContext:
    """Get the current request context."""
    return _request_context.get()


def set_request_context(ctx: RequestContext) -> None:
    """Set the request context for the current async task."""
    _request_context.set(ctx)


def clear_request_context() -> None:
    """Reset the request context after request completes."""
    _request_context.set(RequestContext())
