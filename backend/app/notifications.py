import logging
import smtplib
from datetime import timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

from .config import GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_TO_EMAIL
from .models import Company, StatusCheck, StatusEnum

log = logging.getLogger("notifications")

IST = ZoneInfo("Asia/Kolkata")

# Same fixed status palette used on the dashboard — never themed, so an email
# and the dashboard always agree on what a color means.
STATUS_COLOR = {
    StatusEnum.active: "#0ca30c",
    StatusEnum.delinquent: "#ec835a",
    StatusEnum.forfeited: "#d03b3b",
    StatusEnum.suspended: "#d03b3b",
    StatusEnum.manual_review_needed: "#fab219",
    StatusEnum.unknown: "#898781",
}


def _format_ist(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def _status_label(status: StatusEnum) -> str:
    return status.value.replace("_", " ").title()


def _render_html(company: Company, check: StatusCheck) -> str:
    color = STATUS_COLOR.get(check.status, "#898781")
    status_label = _status_label(check.status)
    checked_at = _format_ist(check.checked_at)
    source_html = (
        f'<a href="{check.source_url}" style="color:{color};font-weight:600;text-decoration:none;">'
        f"View source →</a>"
        if check.source_url
        else '<span style="color:#8891a5;">No source available</span>'
    )

    return f"""\
<html>
  <body style="margin:0;padding:0;background:#eef1f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f7;padding:32px 0;">
      <tr>
        <td align="center">
          <table width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 2px 10px rgba(27,42,74,0.08);">
            <tr>
              <td style="background:#1b2a4a;padding:20px 28px;">
                <span style="color:#ffffff;font-size:15px;font-weight:700;">Franchise Tax Status Monitoring</span>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;">
                <div style="display:inline-block;background:{color}22;color:{color};font-weight:700;font-size:13px;padding:6px 14px;border-radius:999px;margin-bottom:16px;">
                  {status_label}
                </div>
                <h2 style="margin:0 0 4px;color:#1b2a4a;font-size:20px;">{company.name}</h2>
                <p style="margin:0 0 20px;color:#8891a5;font-size:14px;">{company.state}</p>

                <table width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;color:#1b2a4a;border-top:1px solid #e4e8f0;padding-top:16px;">
                  <tr>
                    <td style="padding:6px 0;color:#8891a5;">Status</td>
                    <td style="padding:6px 0;text-align:right;font-weight:600;">{status_label}</td>
                  </tr>
                  <tr>
                    <td style="padding:6px 0;color:#8891a5;">Checked at</td>
                    <td style="padding:6px 0;text-align:right;">{checked_at}</td>
                  </tr>
                  <tr>
                    <td style="padding:6px 0;color:#8891a5;">Source</td>
                    <td style="padding:6px 0;text-align:right;">{source_html}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;background:#f7f9fc;border-top:1px solid #e4e8f0;">
                <span style="color:#8891a5;font-size:12px;">
                  This status changed since the last check. You're receiving this because email alerts are enabled for this dashboard.
                </span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def _render_text(company: Company, check: StatusCheck) -> str:
    return (
        f"Franchise Tax Status Monitoring\n\n"
        f"Company: {company.name}\n"
        f"State: {company.state}\n"
        f"Status: {_status_label(check.status)}\n"
        f"Checked at: {_format_ist(check.checked_at)}\n"
        f"Source: {check.source_url or 'No source available'}\n"
    )


def _send_email(subject: str, text_body: str, html_body: str):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not ALERT_TO_EMAIL:
        log.info(f"Email alert skipped (GMAIL_USER/GMAIL_APP_PASSWORD/ALERT_TO_EMAIL not set): {subject}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ALERT_TO_EMAIL
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

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
    subject = f"[Tax Status Alert] {company.name} ({company.state}) is now {_status_label(check.status)}"
    _send_email(subject, _render_text(company, check), _render_html(company, check))
