import logging
from datetime import datetime, timezone, timedelta

from app.database import get_supabase

logger = logging.getLogger(__name__)

# ── Retention thresholds (days) ───────────────────────────────────────────────
_TABLES: dict[str, dict] = {
    "login_attempts":  {"days": 90,  "ts_col": "created_at"},
    "login_sessions":  {"days": 90,  "ts_col": "created_at"},
    "permission_audit": {"days": 365, "ts_col": "created_at"},
    "audit_log":        {"days": 365, "ts_col": "created_at"},
}


def purge_old_security_data(dry_run: bool = False) -> dict[str, int]:
    """Delete (or count) rows older than the configured threshold per table.

    Returns {table_name: row_count} where count is:
      - dry_run=True:  number of rows that WOULD be deleted (no actual delete)
      - dry_run=False: number of rows actually deleted
      - -1:            table operation failed (logged separately)

    Each table is isolated in its own try/except; a failure on one table
    does not prevent processing the others.
    """
    client = get_supabase()
    results: dict[str, int] = {}

    for table, cfg in _TABLES.items():
        days   = cfg["days"]
        ts_col = cfg["ts_col"]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        try:
            if dry_run:
                resp = (
                    client.table(table)
                    .select("id", count="exact")
                    .lt(ts_col, cutoff)
                    .execute()
                )
                count = resp.count or 0
                logger.info(
                    f"[RETENTION DRY-RUN] {table}: {count} rows would be purged "
                    f"(older than {days}d / before {cutoff})"
                )
            else:
                resp = (
                    client.table(table)
                    .delete()
                    .lt(ts_col, cutoff)
                    .execute()
                )
                count = len(resp.data) if resp.data else 0
                logger.info(
                    f"[RETENTION] {table}: purged {count} rows "
                    f"(older than {days}d / before {cutoff})"
                )
            results[table] = count

        except Exception as e:
            logger.error(
                f"[RETENTION] {table}: failed — {type(e).__name__}: {e}"
            )
            results[table] = -1  # -1 signals a per-table error

    return results
