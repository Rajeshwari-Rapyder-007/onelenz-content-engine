from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ConnectResponse(BaseModel):
    auth_url: str
    state: str


class CallbackRequest(BaseModel):
    code: str
    state: str


class CallbackResponse(BaseModel):
    status: str
    message: str


class StatusResponse(BaseModel):
    status: str
    provider: Optional[str] = None
    user_email: Optional[str] = None
    total_emails_synced: Optional[int] = None
    last_sync_at: Optional[datetime] = None
    sync_frequency: Optional[str] = None
    initial_sync_complete: Optional[bool] = None
    connected_at: Optional[datetime] = None


class DisconnectResponse(BaseModel):
    message: str
