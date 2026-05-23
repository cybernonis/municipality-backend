from app.database import supabase
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

SLA_STATUS = {
    'ok':        {'label': 'Εντός SLA',    'color': 'green',  'icon': '🟢'},
    'warning':   {'label': 'Προειδοποίηση','color': 'yellow', 'icon': '🟡'},
    'breach':    {'label': 'Παράβαση SLA', 'color': 'red',    'icon': '🔴'},
    'escalated': {'label': 'Κλιμάκωση',   'color': 'purple', 'icon': '🚨'},
}

def get_sla_target(category: str, severity: str) -> int:
    """Επιστρέφει target hours από sla_rules"""
    result = supabase.table("sla_rules")\
        .select("target_hours")\
        .eq("category", category)\
        .eq("severity", severity)\
        .execute()
    return result.data[0]["target_hours"] if result.data else 48

def calculate_sla_status(created_at: str, category: str, severity: str) -> dict:
    """Υπολογίζει SLA status για ένα report"""
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    elapsed_hours = (now - created).total_seconds() / 3600
    target_hours = get_sla_target(category, severity)
    percentage = (elapsed_hours / target_hours * 100) if target_hours > 0 else 0

    if percentage >= 150:
        status = 'escalated'
    elif percentage >= 100:
        status = 'breach'
    elif percentage >= 80:
        status = 'warning'
    else:
        status = 'ok'

    remaining_hours = max(0, target_hours - elapsed_hours)

    return {
        'status': status,
        'elapsed_hours': round(elapsed_hours, 1),
        'target_hours': target_hours,
        'percentage': round(percentage, 1),
        'remaining_hours': round(remaining_hours, 1),
        **SLA_STATUS[status]
    }

def check_sla_violations():
    """Ελέγχει όλα τα open tickets για SLA violations"""
    logger.info("🔍 Checking SLA violations...")

    # Πάρε όλα τα open reports
    result = supabase.table("reports")\
        .select("id, category, severity, status, created_at, department_id, assigned_to")\
        .in_("status", ["submitted", "assigned", "in_progress"])\
        .execute()

    if not result.data:
        return []

    violations = []
    warnings = []

    for report in result.data:
        sla = calculate_sla_status(
            report["created_at"],
            report.get("category", "other"),
            report.get("severity", "medium")
        )

        if sla["status"] == "breach":
            violations.append({**report, "sla": sla})
            logger.warning(f"🔴 SLA BREACH: Report {report['id'][:8]} - {sla['percentage']}%")

        elif sla["status"] == "escalated":
            violations.append({**report, "sla": sla})
            logger.error(f"🚨 ESCALATED: Report {report['id'][:8]} - {sla['percentage']}%")

        elif sla["status"] == "warning":
            warnings.append({**report, "sla": sla})
            logger.warning(f"🟡 WARNING: Report {report['id'][:8]} - {sla['percentage']}%")

    logger.info(f"✅ SLA Check complete: {len(violations)} violations, {len(warnings)} warnings")
    return violations + warnings

def get_all_reports_with_sla():
    """Επιστρέφει όλα τα open reports με SLA status"""
    result = supabase.table("reports")\
        .select("*, departments(name)")\
        .in_("status", ["submitted", "assigned", "in_progress"])\
        .order("created_at", desc=False)\
        .execute()

    if not result.data:
        return []

    reports_with_sla = []
    for report in result.data:
        sla = calculate_sla_status(
            report["created_at"],
            report.get("category", "other"),
            report.get("severity", "medium")
        )
        reports_with_sla.append({**report, "sla": sla})

    # Ταξινόμηση: escalated → breach → warning → ok
    priority = {"escalated": 0, "breach": 1, "warning": 2, "ok": 3}
    reports_with_sla.sort(key=lambda x: priority.get(x["sla"]["status"], 4))

    return reports_with_sla