"""
Smoke tests against the production Railway deployment.
These do NOT spin up a local server — they hit the live URL.
"""
import httpx
import pytest

BASE = "https://municipality-backend-production.up.railway.app"


def test_root_returns_200_and_running():
    r = httpx.get(f"{BASE}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "running"


def test_login_bad_credentials_returns_401_not_500():
    r = httpx.post(
        f"{BASE}/auth/login",
        json={"email": "nosuchuser@example.com", "password": "wrongpassword"},
        timeout=15,
    )
    assert r.status_code == 401


def test_announcements_list_returns_200():
    r = httpx.get(f"{BASE}/announcements/", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "total" in body
