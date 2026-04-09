from .codes import ErrorCode


class AppError(Exception):
    """Base application error. Raise with a centralized ErrorCode."""

    def __init__(self, error: ErrorCode, detail: str | None = None):
        self.code = error.code
        self.message = detail or error.message
        self.status_code = error.status_code
        super().__init__(self.message)
