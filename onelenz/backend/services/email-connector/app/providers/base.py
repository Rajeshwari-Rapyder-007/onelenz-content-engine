from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TokenResponse:
    """Token response from OAuth provider."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"
    scope: str = ""


@dataclass
class UserProfile:
    """User profile from OAuth provider."""

    upn: str
    tenant_id: str
    display_name: Optional[str] = None


class BaseOAuthProvider(ABC):
    """Abstract interface for OAuth providers. Implement for each email provider."""

    @abstractmethod
    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        """Build the OAuth authorization URL."""

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> TokenResponse:
        """Exchange authorization code for access + refresh tokens."""

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Use refresh token to get a new access token."""

    @abstractmethod
    async def get_user_profile(self, access_token: str) -> UserProfile:
        """Fetch user profile (email, tenant) from the provider."""
