import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings


def send_email(to: str, subject: str, html_body: str) -> None:
    """Send an email through Gmail SMTP using the credentials in .env.

    SMTP_USER/SMTP_PASSWORD must be a Gmail address + App Password
    (Google Account -> Security -> 2-Step Verification -> App passwords).
    """
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
    message["To"] = to
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM_ADDRESS, to, message.as_string())


# Login itself is Google-only. This helper is kept around because the
# next natural feature — emailing someone when they're added to a team — will
# want it; nothing calls it yet.
