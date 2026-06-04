import asyncio
import json
import logging
import os
from typing import List

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from app.config import settings
from app.limiter import limiter
from app.routers import departments, auth, reports, ai, participation, performance, payments
from app.routers import crisis, sla, predictive, iot, digital_twin
from app.routers import external
from app.routers import announcements, appointments, smart_tips
from app.routers import gamification, carbon
from app.routers import gdpr
from app.routers import places
from app.routers import traffic
from app.routers import closed_roads
from app.routers import ai_actions
from app.services.sla_service import check_sla_violations
from app.routers import staff
from app.routers import admin

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


# ── Sentry — initialize BEFORE app = FastAPI() ────────────────────────────────

_SENSITIVE_KEYS = frozenset({
    "password", "token", "access_token", "refresh_token",
    "secret", "apikey", "api_key", "authorization", "cookie",
})


def _scrub_dict(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if k.lower() in _SENSITIVE_KEYS:
            out[k] = "[Filtered]"
        elif isinstance(v, dict):
            out[k] = _scrub_dict(v)
        else:
            out[k] = v
    return out


def _before_send(event: dict, hint: dict) -> dict:
    req = event.get("request", {})
    if isinstance(req.get("headers"), dict):
        req["headers"] = _scrub_dict(req["headers"])
    if isinstance(req.get("cookies"), dict):
        req["cookies"] = {k: "[Filtered]" for k in req["cookies"]}
    if isinstance(req.get("data"), dict):
        req["data"] = _scrub_dict(req["data"])
    for section in ("extra", "contexts"):
        if isinstance(event.get(section), dict):
            event[section] = _scrub_dict(event[section])
    return event


if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        before_send=_before_send,
        environment=settings.environment,
    )
    logger.info("[SENTRY] Initialized (environment=%s)", settings.environment)
else:
    logger.debug("[SENTRY] DSN not set — error tracking disabled")


# ─────────────────────────────────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


app = FastAPI(
    title="Municipality Reports API",
    description="Smart Municipality Issue Reporting System — Ηράκλειο",
    version="1.0.0",
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

_DEFAULT_ORIGINS = [
    "https://municipality-dashboard-alpha.vercel.app",
    "https://municipality-dashboard.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
]
_ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", ",".join(_DEFAULT_ORIGINS)).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

app.include_router(auth.router,          prefix="/auth",          tags=["Auth"])
app.include_router(reports.router,       prefix="/reports",       tags=["Reports"])
app.include_router(ai.router,            prefix="/ai",            tags=["AI"])
app.include_router(departments.router,   prefix="/departments",   tags=["Departments"])
app.include_router(participation.router, prefix="/participation", tags=["Participation"])
app.include_router(performance.router,   prefix="/performance",   tags=["Performance"])
app.include_router(payments.router,      prefix="/payments",      tags=["Payments"])
app.include_router(crisis.router,        prefix="/crisis",        tags=["Crisis"])
app.include_router(sla.router,           prefix="/sla",           tags=["SLA"])
app.include_router(predictive.router,    prefix="/predictive",    tags=["Predictive"])
app.include_router(iot.router,           prefix="/iot",           tags=["IoT"])
app.include_router(digital_twin.router,  prefix="/digital-twin",  tags=["Digital Twin"])
app.include_router(external.router,       prefix="/external",       tags=["External Data"])
app.include_router(staff.router,          prefix="/staff",          tags=["Staff"])
app.include_router(announcements.router,  prefix="/announcements",  tags=["Announcements"])
app.include_router(appointments.router,   prefix="/appointments",   tags=["Appointments"])
app.include_router(smart_tips.router,     prefix="/smart-tips",     tags=["Smart Tips"])
app.include_router(gamification.router,   prefix="/gamification",   tags=["Gamification"])
app.include_router(carbon.router,         prefix="/carbon",         tags=["Carbon"])
app.include_router(gdpr.router,           prefix="/gdpr",           tags=["GDPR"])
app.include_router(places.router,         prefix="/places",         tags=["Places"])
app.include_router(traffic.router,        prefix="/traffic",        tags=["Traffic"])
app.include_router(closed_roads.router,   prefix="/closed-roads",   tags=["Closed Roads"])
app.include_router(ai_actions.router)
app.include_router(admin.router,          prefix="/admin",          tags=["Admin"])

@app.get("/")
def root():
    return {"message": "Municipality Reports API", "status": "running", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# ─────────────────────────────────────────────
# WebSocket connection manager
# ─────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(json.dumps(message, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ─────────────────────────────────────────────
# APScheduler — sync jobs (SLA)
# ─────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.add_job(check_sla_violations, "interval", minutes=15)
scheduler.start()


# ─────────────────────────────────────────────
# Async background monitoring for external data
# ─────────────────────────────────────────────
async def _monitor_loop(fetch_fn, interval_seconds: int, label: str):
    """Generic monitoring loop: fetch → check thresholds → broadcast alerts → email."""
    from app.services.external_service import check_thresholds
    from app.services.email_service import send_external_alert_email

    # Stagger start so all loops don't fire simultaneously
    await asyncio.sleep(5)

    while True:
        try:
            await fetch_fn()  # primes cache
            alerts = await check_thresholds()
            if alerts:
                await manager.broadcast({
                    "type": "external_alert",
                    "source": label,
                    "alerts": alerts,
                })
                # Email για κάθε alert
                for alert in alerts:
                    try:
                        await send_external_alert_email(
                            alert_type=alert.get("type", "unknown"),
                            message=alert.get("message", "")
                        )
                    except Exception as e:
                        logger.error(f"External alert email error: {e}")

        except Exception as e:
            logger.error(f"[{label}] monitoring error: {e}")
        await asyncio.sleep(interval_seconds)


@app.on_event("startup")
async def start_external_monitoring():
    from app.services.external_service import (
        fetch_weather, fetch_traffic, fetch_hazards,
        fetch_air_quality, fetch_earthquakes,
    )
    from app.services.external_data import (
        get_marine_data, get_pollen_data, get_uv_solar_data,
    )

    # v1 loops
    asyncio.create_task(_monitor_loop(fetch_weather,     600,  "weather"))      # 10 min
    asyncio.create_task(_monitor_loop(fetch_traffic,     120,  "traffic"))      # 2 min
    asyncio.create_task(_monitor_loop(fetch_hazards,     900,  "hazards"))      # 15 min
    asyncio.create_task(_monitor_loop(fetch_air_quality, 1800, "air_quality"))  # 30 min
    asyncio.create_task(_monitor_loop(fetch_earthquakes, 1800, "earthquakes"))  # 30 min

    # v2 loops (beaches & ships refresh via cache TTL; marine/pollen/uv need active refresh)
    asyncio.create_task(_monitor_loop(get_marine_data,  1800, "marine"))        # 30 min
    asyncio.create_task(_monitor_loop(get_pollen_data,  3600, "pollen"))        # 1 h
    asyncio.create_task(_monitor_loop(get_uv_solar_data, 1800, "uv_solar"))     # 30 min


@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown()


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)