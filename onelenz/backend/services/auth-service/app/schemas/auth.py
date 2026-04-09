from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    first_name: str = Field(min_length=1,max_length=100)
    last_name: str = Field(min_length=1,max_length=100)
    company_name: Optional[str] = Field(default=None, max_length=200)
    mobile: Optional[str] = Field(default=None, max_length=30)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthTokenResponse(BaseModel):
    user_id: str
    entity_id: str
    email: str
    display_name: str
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class LogoutResponse(BaseModel):
    message: str = "Logged out successfully"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=255)


class MessageResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
