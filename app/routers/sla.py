from fastapi import APIRouter
from app.services.sla_service import (
    get_all_reports_with_sla,
    check_sla_violations,
    calculate_sla_status
)

router = APIRouter()

@router.get("/status")
def get_sla_status():
    """Όλα τα open reports με SLA status"""
    return get_all_reports_with_sla()

@router.get("/violations")
def get_violations():
    """Μόνο τα reports με SLA violation"""
    all_reports = get_all_reports_with_sla()
    return [r for r in all_reports if r["sla"]["status"] in ["breach", "escalated"]]

@router.get("/warnings")
def get_warnings():
    """Reports με warning"""
    all_reports = get_all_reports_with_sla()
    return [r for r in all_reports if r["sla"]["status"] == "warning"]

@router.get("/summary")
def get_sla_summary():
    """Σύνοψη SLA για dashboard"""
    all_reports = get_all_reports_with_sla()

    return {
        "total_open": len(all_reports),
        "ok":        len([r for r in all_reports if r["sla"]["status"] == "ok"]),
        "warning":   len([r for r in all_reports if r["sla"]["status"] == "warning"]),
        "breach":    len([r for r in all_reports if r["sla"]["status"] == "breach"]),
        "escalated": len([r for r in all_reports if r["sla"]["status"] == "escalated"]),
    }

@router.post("/check")
def trigger_sla_check():
    """Manual trigger για SLA check"""
    violations = check_sla_violations()
    return {
        "message": f"SLA check ολοκληρώθηκε — {len(violations)} issues βρέθηκαν",
        "issues": violations
    }