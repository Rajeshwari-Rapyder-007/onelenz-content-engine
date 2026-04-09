import os

import boto3

from shared.logging import get_logger

logger = get_logger(__name__)

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "mock")
SES_FROM_EMAIL = os.getenv("AWS_SES_FROM_EMAIL", "noreply@onelenz.ai")
SES_REGION = os.getenv("AWS_SES_REGION", os.getenv("AWS_REGION", "ap-south-1"))


def _build_otp_body(otp: str) -> str:
    return (
        f"Your OneLenz verification code is: {otp}\n\n"
        f"This code expires in 10 minutes.\n"
        f"If you did not request this, please ignore this email."
    )


async def send_otp_email(to_email: str, otp: str, subject: str = "OneLenz — Password Reset OTP") -> None:
    """Send OTP email. Uses mock (console log) or AWS SES based on EMAIL_PROVIDER env var."""
    body = _build_otp_body(otp)

    if EMAIL_PROVIDER == "mock":
        logger.info(
            f"[MOCK EMAIL] To: {to_email} | Subject: {subject} | OTP: {otp} | Body: {body}",
        )
        return

    # AWS SES
    try:
        ses = boto3.client("ses", region_name=SES_REGION)
        ses.send_email(
            Source=SES_FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body}},
            },
        )
        logger.info("OTP email sent via SES", extra={"x_to": to_email})
    except Exception:
        logger.error("Failed to send OTP email via SES", exc_info=True, extra={"x_to": to_email})
        raise
