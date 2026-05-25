import aiosmtplib
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER", "")       # your@gmail.com
SMTP_PASS = os.getenv("SMTP_PASS", "")       # App Password (16 chars)
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")   # που θα λαμβάνει alerts


async def send_email(to: str, subject: str, html: str):
    """Core send function."""
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured — skipping email")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Δήμος Ηρακλείου <{SMTP_USER}>"
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
        )
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
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
    await send_email(ADMIN_EMAIL, subject, html)


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
    await send_email(ADMIN_EMAIL, subject, html)


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
    await send_email(ADMIN_EMAIL, subject, html)


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
    await send_email(ADMIN_EMAIL, subject, html)