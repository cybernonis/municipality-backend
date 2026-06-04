import logging

from fastapi import APIRouter, Depends

from app.dependencies import require_permission
from app.utils.data_retention import purge_old_security_data

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/retention/purge")
def retention_purge(
    dry_run: bool = True,
    _user: dict = Depends(require_permission("settings:modify")),
):
    """Purge aged security / audit rows from the four retention-managed tables.

    Pass ?dry_run=false to actually delete. Default is dry_run=true (count only).
    Returns {table: count} where -1 means that table's operation failed.
    """
    results = purge_old_security_data(dry_run=dry_run)
    return {"dry_run": dry_run, "results": results}
