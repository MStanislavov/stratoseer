import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


def _send(to: str, subject: str, html_body: str) -> None:
    if not _smtp_configured():
        logger.warning("SMTP not configured, skipping email to %s: %s", to, subject)
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.smtp_from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, to, msg.as_string())
        logger.info("Email sent to %s: %s", to, subject)
    except Exception:
        logger.exception("Failed to send email to %s", to)


def send_verification_email(email: str, token: str) -> None:
    link = f"{settings.app_base_url}/verify-email?token={token}"
    html = (
        "<h2>Verify your email</h2>"
        f'<p>Click <a href="{link}">here</a> to verify your email address.</p>'
        "<p>This link expires in 24 hours.</p>"
    )
    _send(email, "Verify your Stratoseer account", html)


def send_password_reset_email(email: str, token: str) -> None:
    link = f"{settings.app_base_url}/reset-password?token={token}"
    html = (
        "<h2>Reset your password</h2>"
        f'<p>Click <a href="{link}">here</a> to reset your password.</p>'
        "<p>This link expires in 1 hour.</p>"
    )
    _send(email, "Reset your Stratoseer password", html)
