"""Public/personal email domain blocklist.

Used to prevent signups with personal email addresses.
OneLenz is B2B — users must sign up with a company email.
"""

BLOCKED_DOMAINS = frozenset({
    # Google
    "gmail.com",
    "googlemail.com",
    # Microsoft
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    # Yahoo
    "yahoo.com",
    "yahoo.co.in",
    "ymail.com",
    # Apple
    "icloud.com",
    "me.com",
    "mac.com",
    # Others
    "aol.com",
    "protonmail.com",
    "proton.me",
    "zoho.com",
    "mail.com",
    "gmx.com",
    "tutanota.com",
    "fastmail.com",
    "yandex.com",
    "rediffmail.com",
})


def is_public_domain(domain: str) -> bool:
    """Check if a domain is a public/personal email provider."""
    return domain.lower() in BLOCKED_DOMAINS
