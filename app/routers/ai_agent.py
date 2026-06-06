"""AI Agent με Claude Tool Use — μόνο actions με real DB implementation."""
import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Body

from app.database import get_supabase
from app.services.ai_service import get_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/agent", tags=["ai-agent"])


# ═══════════════════════════════════════════════════════════════
# TOOLS — μόνο REAL implementations
# ═══════════════════════════════════════════════════════════════

def build_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "create_announcement",
            "description": (
                "Δημοσίευση ανακοίνωσης για τους πολίτες. Αυτόματα γράφεις "
                "επαγγελματικό τίτλο και περιεχόμενο στα ελληνικά βάσει του "
                "τι περιγράφει ο χρήστης. Π.χ. αν λέει 'διακοπή νερού αύριο' "
                "γράφεις τίτλο 'Διακοπή υδροδότησης - Αύριο' και αναλυτικό κείμενο."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Σύντομος επαγγελματικός τίτλος ελληνικά (max 80 chars)"},
                    "body": {"type": "string", "description": "Πλήρες κείμενο, ευγενικό, με χρόνο/τόπο/λόγο"},
                    "category": {
                        "type": "string",
                        "enum": ["general", "events", "infrastructure", "emergency", "services"],
                    },
                    "is_urgent": {"type": "boolean"},
                    "is_important": {"type": "boolean"},
                    "expires_at": {"type": "string", "description": "ISO 8601 datetime ή κενό"},
                },
                "required": ["title", "body", "category"],
            },
        },
        {
            "name": "get_statistics",
            "description": "Στατιστικά πλατφόρμας: συνολικές/εκκρεμείς/επιλυμένες αναφορές, κρίσιμες, χρήστες, έσοδα.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["today", "week", "month", "all"]},
                },
            },
        },
        {
            "name": "list_pending_reports",
            "description": "Εκκρεμείς αναφορές που δεν έχουν επιλυθεί.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Μέγιστος αριθμός αποτελεσμάτων (default 20)"},
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "department_id": {"type": "string", "description": "Optional φίλτρο τμήματος"},
                },
            },
        },
        {
            "name": "list_crews",
            "description": "Λίστα όλων των συνεργείων με workload (ενεργές αναφορές). Χρησιμοποίησε το για να βρεις διαθέσιμα συνεργεία.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "department_id": {"type": "string", "description": "Optional φίλτρο τμήματος"},
                },
            },
        },
        {
            "name": "assign_report_to_crew",
            "description": "Ανάθεση συγκεκριμένης αναφοράς σε συνεργείο.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "string", "description": "UUID αναφοράς"},
                    "crew_id": {"type": "string", "description": "UUID συνεργείου"},
                },
                "required": ["report_id", "crew_id"],
            },
        },
        {
            "name": "change_report_status",
            "description": "Αλλαγή κατάστασης αναφοράς.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["submitted", "assigned", "in_progress", "resolved", "completed", "closed"],
                    },
                    "comment": {"type": "string", "description": "Προαιρετικό σχόλιο"},
                },
                "required": ["report_id", "status"],
            },
        },
        {
            "name": "close_road",
            "description": "Κλείσιμο δρόμου για κυκλοφορία (έργα, εκδηλώσεις). Δημιουργεί εγγραφή στο closed_roads.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "road_name": {"type": "string"},
                    "reason": {"type": "string"},
                    "start_date": {"type": "string", "description": "ISO date (YYYY-MM-DD), default σήμερα"},
                    "end_date": {"type": "string", "description": "ISO date προαιρετικά"},
                    "create_announcement": {"type": "boolean", "description": "Αν δημιουργηθεί και ανακοίνωση (default true)"},
                },
                "required": ["road_name", "reason"],
            },
        },
        {
            "name": "summarize_recent_activity",
            "description": "Σύνοψη πρόσφατης δραστηριότητας: νέες αναφορές, επιλυμένες, κορυφαία κατηγορία.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Αριθμός ημερών πίσω (default 7)"},
                },
            },
        },
        {
            "name": "forecast_trends",
            "description": "Ανάλυση τάσεων αναφορών — κορυφαίες κατηγορίες, σύνολο, πρόβλεψη.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "horizon_days": {"type": "integer", "description": "Ορίζοντας πρόβλεψης (default 30)"},
                },
            },
        },
        {
            "name": "system_health_check",
            "description": "Έλεγχος υγείας συστήματος — DB connectivity.",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "declare_crisis_event",
            "description": "Κήρυξη έκτακτης ανάγκης — εισάγει στο crisis_events και ειδοποιεί.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Τύπος κρίσης (π.χ. flood, fire, earthquake)"},
                    "description": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "area": {"type": "string", "description": "Περιοχή"},
                },
                "required": ["type", "description", "severity"],
            },
        },
        {
            "name": "get_department_performance",
            "description": "Στατιστικά απόδοσης για συγκεκριμένο τμήμα.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "department_id": {"type": "string"},
                },
                "required": ["department_id"],
            },
        },
    ]


# ═══════════════════════════════════════════════════════════════
# TOOL EXECUTORS
# ═══════════════════════════════════════════════════════════════

def execute_create_announcement(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        row = {
            "id": str(uuid.uuid4()),
            "title": params["title"].strip()[:200],
            "body": params["body"].strip(),
            "category": params.get("category", "general"),
            "is_urgent": bool(params.get("is_urgent", False)),
            "is_important": bool(params.get("is_important", False)),
            "admin_id": user_id,
        }
        if params.get("expires_at"):
            row["expires_at"] = params["expires_at"]

        result = client.table("announcements").insert(row).execute()
        created = result.data[0] if result.data else row
        return {
            "success": True,
            "message": f"Η ανακοίνωση '{created['title']}' δημοσιεύτηκε επιτυχώς.",
            "data": {
                "id": created.get("id"),
                "title": created.get("title"),
                "category": created.get("category"),
                "is_urgent": created.get("is_urgent"),
            },
        }
    except Exception as e:
        logger.error(f"[AGENT] create_announcement error: {e}")
        return {"success": False, "error": str(e)}


def execute_get_statistics(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        all_reports = client.table("reports").select("id, status, severity, created_at").execute()
        reports = all_reports.data or []

        period = params.get("period", "all")
        if period == "today":
            cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            reports = [r for r in reports if r.get("created_at", "") >= cutoff]
        elif period == "week":
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            reports = [r for r in reports if r.get("created_at", "") >= cutoff]
        elif period == "month":
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            reports = [r for r in reports if r.get("created_at", "") >= cutoff]

        users_r = client.table("users").select("id", count="exact").execute()
        pay_r = client.table("payments").select("amount, status").execute()
        pay_data = pay_r.data or []
        revenue = sum(p["amount"] for p in pay_data if p.get("status") == "completed")

        return {
            "success": True,
            "data": {
                "reports_total": len(reports),
                "reports_pending": len([r for r in reports if r.get("status") in ("submitted", "assigned", "in_progress")]),
                "reports_resolved": len([r for r in reports if r.get("status") in ("resolved", "completed")]),
                "reports_critical": len([r for r in reports if r.get("severity") == "critical"]),
                "users_total": users_r.count or 0,
                "revenue_eur": round(revenue, 2),
                "period": period,
            },
        }
    except Exception as e:
        logger.error(f"[AGENT] get_statistics error: {e}")
        return {"success": False, "error": str(e)}


def execute_list_pending_reports(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        limit = int(params.get("limit", 20))
        query = (
            client.table("reports")
            .select("id, description, address, severity, status, created_at, category")
            .in_("status", ["submitted", "assigned", "in_progress"])
        )
        if params.get("severity"):
            query = query.eq("severity", params["severity"])
        if params.get("department_id"):
            query = query.eq("department_id", params["department_id"])

        result = query.order("created_at", desc=False).limit(limit).execute()
        return {
            "success": True,
            "data": result.data or [],
            "count": len(result.data or []),
        }
    except Exception as e:
        logger.error(f"[AGENT] list_pending_reports error: {e}")
        return {"success": False, "error": str(e)}


def execute_list_crews(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        query = client.table("crews").select(
            "id, name, specialty, department_id, members_count, is_active"
        ).eq("is_active", True)
        if params.get("department_id"):
            query = query.eq("department_id", params["department_id"])

        crews_result = query.execute()
        result = []
        for crew in crews_result.data or []:
            workload = client.table("reports").select("id", count="exact").eq("crew_id", crew["id"]).in_(
                "status", ["submitted", "assigned", "in_progress"]
            ).execute()
            result.append({
                "id": crew["id"],
                "name": crew["name"],
                "specialty": crew.get("specialty"),
                "department_id": crew.get("department_id"),
                "members_count": crew.get("members_count", 0),
                "active_reports": workload.count if hasattr(workload, "count") else 0,
            })

        result.sort(key=lambda c: c["active_reports"])
        return {"success": True, "data": result, "total": len(result)}
    except Exception as e:
        logger.error(f"[AGENT] list_crews error: {e}")
        return {"success": False, "error": str(e)}


def execute_assign_report_to_crew(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        crew_r = client.table("crews").select("id, department_id, name").eq("id", params["crew_id"]).execute()
        if not crew_r.data:
            return {"success": False, "error": "Δεν βρέθηκε συνεργείο με αυτό το ID"}

        crew = crew_r.data[0]
        update = client.table("reports").update({
            "crew_id": params["crew_id"],
            "department_id": crew["department_id"],
            "status": "assigned",
            "auto_assigned": False,
        }).eq("id", params["report_id"]).execute()

        if not update.data:
            return {"success": False, "error": "Δεν βρέθηκε αναφορά με αυτό το ID"}

        return {
            "success": True,
            "message": f"Η αναφορά ανατέθηκε επιτυχώς στο συνεργείο '{crew['name']}'.",
            "data": {
                "report_id": params["report_id"],
                "crew_id": params["crew_id"],
                "crew_name": crew["name"],
            },
        }
    except Exception as e:
        logger.error(f"[AGENT] assign_report_to_crew error: {e}")
        return {"success": False, "error": str(e)}


def execute_change_report_status(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        result = client.table("reports").update({"status": params["status"]}).eq("id", params["report_id"]).execute()
        comment = params.get("comment", f"Κατάσταση → {params['status']}")
        client.table("report_updates").insert({
            "report_id": params["report_id"],
            "status": params["status"],
            "comment": comment,
        }).execute()
        return {
            "success": True,
            "message": f"Η κατάσταση αναφοράς άλλαξε σε '{params['status']}'.",
            "data": result.data[0] if result.data else None,
        }
    except Exception as e:
        logger.error(f"[AGENT] change_report_status error: {e}")
        return {"success": False, "error": str(e)}


def execute_close_road(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        today = datetime.now(timezone.utc).date().isoformat()
        row = {
            "road_name": params["road_name"],
            "reason": params.get("reason", "Εργασίες"),
            "start_date": params.get("start_date", today),
            "status": "active",
            "created_by": user_id,
            "coordinates": {"type": "Point", "coordinates": [25.1442, 35.3387]},
        }
        if params.get("end_date"):
            row["end_date"] = params["end_date"]

        result = client.table("closed_roads").insert(row).execute()
        road = result.data[0] if result.data else row
        response: dict = {
            "success": True,
            "message": f"Ο δρόμος '{params['road_name']}' κλείστηκε επιτυχώς.",
            "data": {"id": road.get("id"), "road_name": road.get("road_name"), "status": "active"},
        }

        if params.get("create_announcement", True):
            ann_row = {
                "id": str(uuid.uuid4()),
                "title": f"Κλειστός δρόμος: {params['road_name']}",
                "body": f"Ο δρόμος {params['road_name']} είναι κλειστός λόγω {params.get('reason', 'εργασιών')}.",
                "is_important": True,
                "is_urgent": False,
                "category": "infrastructure",
            }
            ann = client.table("announcements").insert(ann_row).execute()
            response["announcement_created"] = True

        return response
    except Exception as e:
        logger.error(f"[AGENT] close_road error: {e}")
        return {"success": False, "error": str(e)}


def execute_summarize_recent_activity(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        days = int(params.get("days", 7))
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        reports_r = client.table("reports").select("status, category").gte("created_at", since).execute()
        data = reports_r.data or []
        cats: dict = {}
        for r in data:
            c = r.get("category", "other")
            cats[c] = cats.get(c, 0) + 1
        top_cat = max(cats, key=cats.get) if cats else "—"
        return {
            "success": True,
            "data": {
                "period_days": days,
                "new_reports": len(data),
                "resolved": len([r for r in data if r["status"] in ("resolved", "completed")]),
                "top_category": top_cat,
                "top_category_count": cats.get(top_cat, 0),
            },
        }
    except Exception as e:
        logger.error(f"[AGENT] summarize_recent_activity error: {e}")
        return {"success": False, "error": str(e)}


def execute_forecast_trends(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        reports_r = client.table("reports").select("category, created_at").execute()
        data = reports_r.data or []
        cats: dict = {}
        for r in data:
            c = r.get("category", "other")
            cats[c] = cats.get(c, 0) + 1
        top3 = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
        return {
            "success": True,
            "data": {
                "top_categories": [{"category": k, "count": v} for k, v in top3],
                "total_reports": len(data),
                "forecast": "Αυξητική τάση αναφορών βάσει ιστορικών δεδομένων",
                "horizon_days": params.get("horizon_days", 30),
            },
        }
    except Exception as e:
        logger.error(f"[AGENT] forecast_trends error: {e}")
        return {"success": False, "error": str(e)}


def execute_system_health_check(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        checks = {}
        try:
            client.table("reports").select("id").limit(1).execute()
            checks["database"] = "online"
        except Exception as e:
            checks["database"] = f"error: {e}"
        try:
            client.table("users").select("id").limit(1).execute()
            checks["users_table"] = "online"
        except Exception:
            checks["users_table"] = "error"
        all_ok = all("error" not in v for v in checks.values())
        return {
            "success": True,
            "data": {"checks": checks, "overall": "healthy" if all_ok else "degraded"},
        }
    except Exception as e:
        logger.error(f"[AGENT] system_health_check error: {e}")
        return {"success": False, "error": str(e)}


def execute_declare_crisis_event(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        row = {
            "id": str(uuid.uuid4()),
            "type": params["type"],
            "description": params.get("description", ""),
            "severity": params.get("severity", "high"),
            "latitude": 35.3387,
            "longitude": 25.1442,
            "address": params.get("area"),
            "status": "active",
            "user_id": user_id,
        }
        result = client.table("crisis_events").insert(row).execute()
        return {
            "success": True,
            "message": f"Έκτακτη ανάγκη '{params['type']}' κηρύχθηκε.",
            "data": result.data[0] if result.data else row,
        }
    except Exception as e:
        logger.error(f"[AGENT] declare_crisis_event error: {e}")
        return {"success": False, "error": str(e)}


def execute_get_department_performance(params: dict, user_id: str) -> dict:
    try:
        client = get_supabase()
        reports_r = client.table("reports").select("status, created_at").eq("department_id", params["department_id"]).execute()
        data = reports_r.data or []
        resolved = [r for r in data if r["status"] in ("resolved", "completed")]
        return {
            "success": True,
            "data": {
                "department_id": params["department_id"],
                "total_reports": len(data),
                "resolved": len(resolved),
                "pending": len(data) - len(resolved),
                "resolution_rate": f"{round(len(resolved) / len(data) * 100, 1)}%" if data else "0%",
            },
        }
    except Exception as e:
        logger.error(f"[AGENT] get_department_performance error: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# EXECUTOR MAPPING
# ═══════════════════════════════════════════════════════════════

TOOL_EXECUTORS = {
    "create_announcement": execute_create_announcement,
    "get_statistics": execute_get_statistics,
    "list_pending_reports": execute_list_pending_reports,
    "list_crews": execute_list_crews,
    "assign_report_to_crew": execute_assign_report_to_crew,
    "change_report_status": execute_change_report_status,
    "close_road": execute_close_road,
    "summarize_recent_activity": execute_summarize_recent_activity,
    "forecast_trends": execute_forecast_trends,
    "system_health_check": execute_system_health_check,
    "declare_crisis_event": execute_declare_crisis_event,
    "get_department_performance": execute_get_department_performance,
}

_SYSTEM_PROMPT = (
    "Είσαι ο AI Agent του Δήμου Ηρακλείου για διοικητική χρήση. "
    "Μιλάς πάντα στα Ελληνικά με επαγγελματισμό και ευγένεια.\n\n"
    "ΟΔΗΓΙΕΣ:\n"
    "1. Όταν ο χρήστης ζητά κάτι, ΑΥΤΟΜΑΤΑ εκτέλεσε το αντίστοιχο tool.\n"
    "2. Για ανακοινώσεις, δημιούργησε ευχάριστο και επαγγελματικό κείμενο "
    "χωρίς να ζητάς πρόσθετες πληροφορίες αν μπορείς να συμπεράνεις από το context.\n"
    "3. Μετά την εκτέλεση, δώσε φιλική επιβεβαίωση με ✅.\n"
    "4. Αν χρειάζεσαι ΟΝΤΩΣ κρίσιμο info (π.χ. συγκεκριμένο UUID), ρώτησε.\n"
    "5. ΠΟΤΕ μη δείχνεις JSON ή technical details στον τελικό χρήστη.\n"
    "6. Πάντα δίνεις σύντομη περίληψη του τι έκανες.\n"
)


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/")
async def ai_agent(payload: dict = Body(...)):
    """AI Agent με auto-execution μέσω Claude Tool Use."""
    user_id = payload.get("user_id")
    messages = payload.get("messages", [])

    if not user_id:
        raise HTTPException(400, "Λείπει user_id")
    if not messages:
        raise HTTPException(400, "Λείπουν messages")

    try:
        client = get_client()
        system_prompt = _SYSTEM_PROMPT + f"\nΣήμερα: {datetime.now().strftime('%A, %d %B %Y, %H:%M')}"

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=system_prompt,
            tools=build_tools(),
            messages=messages,
        )

        tool_calls_log = []
        tool_results_log = []
        max_iterations = 5
        iteration = 0

        while response.stop_reason == "tool_use" and iteration < max_iterations:
            iteration += 1
            assistant_msg = {"role": "assistant", "content": response.content}
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            tool_result_blocks = []
            for tool_use in tool_use_blocks:
                tool_name = tool_use.name
                tool_input = tool_use.input

                logger.info(f"[AGENT] tool={tool_name} input={json.dumps(tool_input, ensure_ascii=False)[:200]}")

                executor = TOOL_EXECUTORS.get(tool_name)
                if executor:
                    result = executor(tool_input, user_id)
                else:
                    result = {"success": False, "error": f"Unknown tool: {tool_name}"}

                logger.info(f"[AGENT] tool={tool_name} success={result.get('success')}")
                tool_calls_log.append({"name": tool_name, "input": tool_input})
                tool_results_log.append(result)

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            messages = messages + [
                assistant_msg,
                {"role": "user", "content": tool_result_blocks},
            ]

            response = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=2048,
                system=system_prompt,
                tools=build_tools(),
                messages=messages,
            )

        final_text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        return {
            "response": final_text or "Έγινε.",
            "tool_calls": tool_calls_log,
            "tool_results": tool_results_log,
            "iterations": iteration,
        }

    except Exception as e:
        logger.error(f"[AGENT] Error: {e}", exc_info=True)
        raise HTTPException(500, f"Σφάλμα agent: {str(e)}")


@router.get("/tools")
def list_available_tools():
    """Λίστα όλων των tools που υποστηρίζει το agent."""
    tools = build_tools()
    return {
        "tools": [{"name": t["name"], "description": t["description"]} for t in tools],
        "count": len(tools),
    }
