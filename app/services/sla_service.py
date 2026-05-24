from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Hardcoded SLA targets — αποφεύγουμε extra DB queries
SLA_TARGETS = {
    ('road_damage',  'high'):   4,
    ('road_damage',  'medium'): 48,
    ('road_damage',  'low'):    168,
    ('lighting',     'high'):   2,
    ('lighting',     'medium'): 24,
    ('lighting',     'low'):    72,
    ('water_leak',   'high'):   1,
    ('water_leak',   'medium'): 12,
    ('water_leak',   'low'):    48,
    ('waste',        'high'):   8,
    ('waste',        'medium'): 24,
    ('waste',        'low'):    72,
    ('vandalism',    'high'):   24,
    ('vandalism',    'medium'): 120,
    ('vandalism',    'low'):    336,
    ('fallen_tree',  'high'):   48,
    ('fallen_tree',  'medium'): 168,
    ('fallen_tree',  'low'):    720,
}

SLA_STATUS = {
    'ok':        {'label': 'Εντός SLA',     'color': 'green',  'icon': '🟢'},
    'warning':   {'label': 'Προειδοποίηση', 'color': 'yellow', 'icon': '🟡'},
    'breach':    {'label': 'Παράβαση SLA',  'color': 'red',    'icon': '🔴'},
    'escalated': {'label': 'Κλιμάκωση',    'color': 'purple', 'icon': '🚨'},
}

def get_sla_target(category: str, severity: str) -> int:
    return SLA_TARGETS.get((category, severity), 48)

def calculate_sla_status(created_at: str, category: str, severity: str) -> dict:
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
    from app.database import supabase
    import asyncio
    from app.services.email_service import send_sla_breach_email

    logger.info("🔍 Checking SLA violations...")

    result = supabase.table("reports")\
        .select("id, category, severity, status, created_at")\
        .in_("status", ["submitted", "assigned", "in_progress"])\
        .execute()

    if not result.data:
        return []

    violations = []
    for report in result.data:
        sla = calculate_sla_status(
            report["created_at"],
            report.get("category", "other"),
            report.get("severity", "medium")
        )
        if sla["status"] in ["breach", "escalated", "warning"]:
            violations.append({**report, "sla": sla})
            logger.warning(f"{sla['icon']} Report {report['id'][:8]}: {sla['percentage']}%")

            # Email μόνο για breach/escalated (όχι warning)
            if sla["status"] in ["breach", "escalated"]:
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(send_sla_breach_email(
                        report_id=report["id"][:8],
                        category=report.get("category", "other"),
                        hours_overdue=sla["elapsed_hours"] - sla["target_hours"]
                    ))
                    loop.close()
                except Exception as e:
                    logger.error(f"SLA email error: {e}")

    logger.info(f"✅ Done: {len(violations)} issues")
    return violations

def get_all_reports_with_sla():
    from app.database import supabase

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

    priority = {"escalated": 0, "breach": 1, "warning": 2, "ok": 3}
    reports_with_sla.sort(key=lambda x: priority.get(x["sla"]["status"], 4))

    return reports_with_sla