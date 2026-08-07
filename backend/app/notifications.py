import logging
import smtplib
from email.mime.text import MIMEText

from .config import GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_TO_EMAIL
from .models import Company, StatusCheck, StatusEnum

log = logging.getLogger("notifications")


def _send_email(subject: str, body: str):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not ALERT_TO_EMAIL:
        log.info(f"Email alert skipped (GMAIL_USER/GMAIL_APP_PASSWORD/ALERT_TO_EMAIL not set): {subject}")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ALERT_TO_EMAIL

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, [ALERT_TO_EMAIL], msg.as_string())
        log.info(f"Email alert sent: {subject}")
    except Exception as e:
        log.info(f"Email alert failed to send ({type(e).__name__}: {e}): {subject}")


def maybe_alert_on_status_change(session, check: StatusCheck):
    """Sends an email only when a check's status is non-active AND differs from
    the company's previous status — first detection or a change, never a repeat
    of the same non-active status on every scheduled re-check."""
    if check.status == StatusEnum.active:
        return

    previous = (
        session.query(StatusCheck)
        .filter(StatusCheck.company_id == check.company_id, StatusCheck.id != check.id)
        .order_by(StatusCheck.checked_at.desc())
        .first()
    )
    if previous is not None and previous.status == check.status:
        return

    company = session.query(Company).filter_by(id=check.company_id).first()
    subject = f"[Tax Status Alert] {company.name} ({company.state}) is now {check.status.value.replace('_', ' ')}"
    body = (
        f"Company: {company.name}\n"
        f"State: {company.state}\n"
        f"Status: {check.status.value.replace('_', ' ')}\n"
        f"Checked at: {check.checked_at}\n"
        f"Source: {check.source_url or 'n/a'}\n"
    )
    _send_email(subject, body)
