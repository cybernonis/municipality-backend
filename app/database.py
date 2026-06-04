from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY

# Service-role singleton — DB/table operations ONLY.
# NEVER call .auth.sign_in / .auth.sign_out / .auth.set_session on this client.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

_client: Client | None = None


def get_supabase() -> Client:
    """Singleton service-role client. Use for .table() queries only."""
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


def get_auth_client() -> Client:
    """Fresh anon-key client per call — safe for all .auth.* operations.
    Never cache: each call returns a new instance with no session attached."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
