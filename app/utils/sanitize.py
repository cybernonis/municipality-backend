import re

import bleach


def sanitize_text(text: str) -> str:
    text = bleach.clean(text, tags=[], strip=True)
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
    return text.strip()


def mask_email(email: str) -> str:
    """Return ste***@***.com style masked email safe for logs."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    parts = domain.rsplit(".", 1)
    tld = "." + parts[-1] if len(parts) > 1 else ""
    return local[:3] + "***@***" + tld
