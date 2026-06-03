import httpx
import logging
from datetime import datetime

from app.config import settings
from app.utils.sanitize import mask_email

logger = logging.getLogger(__name__)

SENDER_NAME = "Δήμος Ηρακλείου"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


async def send_email(to: str, subject: str, html: str):
    logger.debug(f"send_email: to={mask_email(to)} subject={subject[:30]}")
    if not settings.brevo_api_key:
        logger.warning("BREVO_API_KEY not set — skipping email")
        return False
    if not to:
        logger.warning("No recipient email — skipping email")
        return False

    try:
        payload = {
            "sender": {"name": SENDER_NAME, "email": settings.smtp_user},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": settings.brevo_api_key,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(BREVO_URL, json=payload, headers=headers)

        if resp.status_code in (200, 201):
            logger.info(f"Email sent to {mask_email(to)}")
            return True
        else:
            logger.error(f"Brevo error {resp.status_code} for {mask_email(to)}")
            return False

    except Exception as e:
        logger.error(f"Email exception for {mask_email(to)}: {type(e).__name__}")
        return False


# ─────────────────────────────────────────────
# SLA Breach Alert
# ─────────────────────────────────────────────
async def send_sla_breach_email(report_id: str, category: str, hours_overdue: float):
    subject = f"⚠️ SLA Παραβίαση — Αναφορά #{report_id}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#dc2626;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2>⚠️ Παραβίαση SLA</h2>
      </div>
      <div style="padding:20px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px">
        <p><strong>Αναφορά:</strong> #{report_id}</p>
        <p><strong>Κατηγορία:</strong> {category}</p>
        <p><strong>Καθυστέρηση:</strong> {hours_overdue:.1f} ώρες</p>
        <p><strong>Ώρα:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        <a href="https://municipality-dashboard.vercel.app/sla"
           style="background:#dc2626;color:white;padding:10px 20px;
                  border-radius:6px;text-decoration:none;display:inline-block;margin-top:10px">
          Προβολή SLA Dashboard
        </a>
      </div>
    </div>
    """
    await send_email(settings.admin_email, subject, html)


# ─────────────────────────────────────────────
# Crisis Alert
# ─────────────────────────────────────────────
async def send_crisis_email(crisis_type: str, location: str, description: str):
    subject = f"🆘 Κρίση — {crisis_type}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#7c3aed;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2>🆘 Νέα Κατάσταση Κρίσης</h2>
      </div>
      <div style="padding:20px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px">
        <p><strong>Τύπος:</strong> {crisis_type}</p>
        <p><strong>Τοποθεσία:</strong> {location}</p>
        <p><strong>Περιγραφή:</strong> {description}</p>
        <p><strong>Ώρα:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        <a href="https://municipality-dashboard.vercel.app/crisis"
           style="background:#7c3aed;color:white;padding:10px 20px;
                  border-radius:6px;text-decoration:none;display:inline-block;margin-top:10px">
          Προβολή Crisis Dashboard
        </a>
      </div>
    </div>
    """
    await send_email(settings.admin_email, subject, html)


# ─────────────────────────────────────────────
# High Severity Report Alert
# ─────────────────────────────────────────────
async def send_high_severity_email(report_id: str, category: str, description: str, address: str):
    subject = f"🔴 Υψηλή Σοβαρότητα — Αναφορά #{report_id}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#ea580c;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2>🔴 Νέα Αναφορά Υψηλής Σοβαρότητας</h2>
      </div>
      <div style="padding:20px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px">
        <p><strong>Αναφορά:</strong> #{report_id}</p>
        <p><strong>Κατηγορία:</strong> {category}</p>
        <p><strong>Διεύθυνση:</strong> {address}</p>
        <p><strong>Περιγραφή:</strong> {description}</p>
        <p><strong>Ώρα:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        <a href="https://municipality-dashboard.vercel.app/reports/{report_id}"
           style="background:#ea580c;color:white;padding:10px 20px;
                  border-radius:6px;text-decoration:none;display:inline-block;margin-top:10px">
          Προβολή Αναφοράς
        </a>
      </div>
    </div>
    """
    await send_email(settings.admin_email, subject, html)


# ─────────────────────────────────────────────
# External Alert (φωτιά/σεισμός/AQI/καιρός)
# ─────────────────────────────────────────────
async def send_external_alert_email(alert_type: str, message: str):
    icons = {"fire": "🔥", "earthquake": "🌍", "air": "💨", "weather": "⛈️"}
    icon = icons.get(alert_type, "⚠️")
    subject = f"{icon} Εξωτερική Ειδοποίηση — {message[:50]}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#0369a1;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2>{icon} Εξωτερική Ειδοποίηση</h2>
      </div>
      <div style="padding:20px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px">
        <p><strong>Τύπος:</strong> {alert_type}</p>
        <p><strong>Μήνυμα:</strong> {message}</p>
        <p><strong>Ώρα:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        <a href="https://municipality-dashboard.vercel.app/digital-twin"
           style="background:#0369a1;color:white;padding:10px 20px;
                  border-radius:6px;text-decoration:none;display:inline-block;margin-top:10px">
          Προβολή Digital Twin
        </a>
      </div>
    </div>
    """
    await send_email(settings.admin_email, subject, html)
