from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ConsentGrantRequest(BaseModel):
    consent_type: str
    domain_scope: str = "ALL"


class ConsentRevokeRequest(BaseModel):
    consent_type: str


class ConsentStatusResponse(BaseModel):
    consent_type: str
    is_granted: bool
    granted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class ConsentGrantResponse(BaseModel):
    consent_id: int
    consent_type: str
    is_granted: bool
    granted_at: Optional[datetime] = None
