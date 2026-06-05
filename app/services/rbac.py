PERMISSIONS: dict[str, set[str]] = {
    "citizen": {
        "reports:create", "reports:read_own", "reports:update_own",
        "announcements:read", "gamification:participate",
    },
    "worker": {
        "reports:read_all", "reports:update_status",
        "tasks:read_assigned", "tasks:update_status",
        "announcements:read",
    },
    "inspector": {
        "reports:read_all", "reports:update_status", "reports:assign",
        "announcements:read",
    },
    "manager": {
        "reports:*", "announcements:*",
        "departments:read", "iot:view", "staff:manage_dept",
    },
    "admin": {"*:*"},
}


def has_permission(role: str | None, permission: str) -> bool:
    if not role:
        return False
    role = role.strip().lower()
    perms = PERMISSIONS.get(role, set())
    if permission in perms:           # exact match
        return True
    resource, _, _ = permission.partition(":")
    if f"{resource}:*" in perms:     # resource wildcard  e.g. "reports:*"
        return True
    if "*:*" in perms:               # super-admin wildcard
        return True
    return False
