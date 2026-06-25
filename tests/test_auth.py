"""
اختبارات مسارات المصادقة — القطعة 1-ب.
التشغيل:  pytest tests/test_auth.py -v
يستخدم قاعدة بيانات SQLite مؤقتة في الذاكرة (لا تمسّ بياناتك).
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./_test_auth.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.database import engine, Base

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _register(email="a@b.com", pw="password123"):
    return client.post("/auth/register",
                       json={"email": email, "password": pw, "full_name": "تجربة"})


def test_register_creates_user():
    r = _register()
    assert r.status_code == 201
    assert r.json()["email"] == "a@b.com"
    assert "password_hash" not in r.json()  # لا نسرّب التجزئة أبداً


def test_duplicate_email_rejected():
    _register()
    assert _register().status_code == 409


def test_short_password_rejected():
    r = client.post("/auth/register", json={"email": "x@y.com", "password": "123"})
    assert r.status_code == 422  # Pydantic يرفض أقل من 8


def test_login_returns_tokens():
    _register()
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body and "refresh_token" in body


def test_wrong_password_rejected():
    _register()
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "wrong-pass"})
    assert r.status_code == 401


def test_me_requires_token():
    assert client.get("/auth/me").status_code == 401


def test_me_with_token_works():
    _register()
    tok = client.post("/auth/login",
                      json={"email": "a@b.com", "password": "password123"}).json()
    r = client.get("/auth/me",
                   headers={"Authorization": f"Bearer {tok['access_token']}"})
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.com"


def test_refresh_token_cannot_be_used_as_access():
    """الثغرة المعالَجة: توكن refresh يجب ألا يُقبل في مسار محمي."""
    _register()
    tok = client.post("/auth/login",
                      json={"email": "a@b.com", "password": "password123"}).json()
    r = client.get("/auth/me",
                   headers={"Authorization": f"Bearer {tok['refresh_token']}"})
    assert r.status_code == 401


def test_refresh_issues_new_access():
    _register()
    tok = client.post("/auth/login",
                      json={"email": "a@b.com", "password": "password123"}).json()
    r = client.post("/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200
    assert "access_token" in r.json()
