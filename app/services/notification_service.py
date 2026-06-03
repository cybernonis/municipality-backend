import json
import logging

import firebase_admin
from firebase_admin import credentials, messaging

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Firebase Admin
_firebase_initialized = False

def _init_firebase():
    global _firebase_initialized
    if _firebase_initialized:
        return True
    try:
        service_account = settings.firebase_service_account
        if not service_account:
            logger.warning("FIREBASE_SERVICE_ACCOUNT not set")
            return False
        
        cred_dict = json.loads(service_account)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("Firebase Admin initialized")
        return True
    except Exception as e:
        logger.error(f"Firebase init error: {e}")
        return False


async def send_push_notification(token: str, title: str, body: str, data: dict = {}):
    """Στέλνει push notification σε ένα device."""
    if not _init_firebase():
        return False
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in data.items()},
            token=token,
        )
        response = messaging.send(message)
        logger.info(f"Push sent: {response}")
        return True
    except Exception as e:
        logger.error(f"Push error: {e}")
        return False


async def send_push_to_multiple(tokens: list, title: str, body: str, data: dict = {}):
    """Στέλνει push notification σε πολλά devices."""
    if not _init_firebase() or not tokens:
        return False
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in data.items()},
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(message)
        logger.info(f"Push multicast: {response.success_count} success, {response.failure_count} failed")
        return True
    except Exception as e:
        logger.error(f"Push multicast error: {e}")
        return False


async def notify_report_status_change(fcm_token: str, report_id: str, status: str):
    """Ειδοποίηση πολίτη για αλλαγή status αναφοράς."""
    status_labels = {
        "submitted":   "Υποβλήθηκε",
        "assigned":    "Ανατέθηκε",
        "in_progress": "Σε εξέλιξη",
        "completed":   "Ολοκληρώθηκε",
        "rejected":    "Απορρίφθηκε",
    }
    label = status_labels.get(status, status)
    return await send_push_notification(
        token=fcm_token,
        title="📋 Ενημέρωση Αναφοράς",
        body=f"Η αναφορά σας #{report_id[:8]} είναι τώρα: {label}",
        data={"report_id": report_id, "status": status}
    )


async def notify_crisis_alert(tokens: list, crisis_type: str, location: str):
    """Ειδοποίηση όλων για κρίση."""
    icons = {
        "fire": "🔥", "flood": "🌊", "earthquake": "🌍",
        "power_outage": "⚡", "accident": "🚗", "medical": "🏥"
    }
    icon = icons.get(crisis_type, "🆘")
    return await send_push_to_multiple(
        tokens=tokens,
        title=f"{icon} Έκτακτη Ανάγκη",
        body=f"Κατάσταση έκτακτης ανάγκης στην περιοχή: {location}",
        data={"type": "crisis", "crisis_type": crisis_type}
    )


async def notify_weather_alert(tokens: list, message: str):
    """Ειδοποίηση για καιρικές συνθήκες."""
    return await send_push_to_multiple(
        tokens=tokens,
        title="⛈️ Καιρική Προειδοποίηση",
        body=message,
        data={"type": "weather"}
    )