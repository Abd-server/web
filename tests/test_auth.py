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


# ───── اختبارات استرجاع/تغيير كلمة المرور (المرحلة أ) ─────

def _login(email="a@b.com", pw="password123"):
    return client.post("/auth/login", json={"email": email, "password": pw})


def test_forgot_password_no_leak():
    """forgot-password يرجّع نفس الرد سواء الإيميل موجود أو لا."""
    _register()
    r1 = client.post("/auth/forgot-password", json={"email": "a@b.com"})
    r2 = client.post("/auth/forgot-password", json={"email": "ghost@x.com"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()  # لا يكشف وجود الإيميل


def test_reset_password_flow():
    """المسار الكامل: طلب رمز → قراءته من القاعدة → إعادة التعيين → دخول بالجديدة."""
    _register()
    client.post("/auth/forgot-password", json={"email": "a@b.com"})
    # نقرأ الرمز مباشرة من القاعدة (في الواقع يصل بالإيميل)
    from app.db.database import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    user = db.query(User).filter(User.email == "a@b.com").first()
    code = user.reset_code
    db.close()
    assert code and len(code) == 6
    # إعادة التعيين
    r = client.post("/auth/reset-password", json={
        "email": "a@b.com", "code": code, "new_password": "newpass456"})
    assert r.status_code == 200 and "access_token" in r.json()
    # القديمة ما تشتغل، الجديدة تشتغل
    assert _login(pw="password123").status_code == 401
    assert _login(pw="newpass456").status_code == 200


def test_reset_wrong_code():
    _register()
    client.post("/auth/forgot-password", json={"email": "a@b.com"})
    r = client.post("/auth/reset-password", json={
        "email": "a@b.com", "code": "000000", "new_password": "newpass456"})
    assert r.status_code == 400


def test_change_password():
    _register()
    tok = _login().json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    # كلمة حالية خاطئة
    assert client.post("/auth/change-password", headers=h, json={
        "current_password": "wrong", "new_password": "newpass456"}).status_code == 400
    # صحيحة
    assert client.post("/auth/change-password", headers=h, json={
        "current_password": "password123", "new_password": "newpass456"}).status_code == 200
    assert _login(pw="newpass456").status_code == 200


def test_change_name():
    _register()
    tok = _login().json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/auth/change-name", headers=h, json={"full_name": "اسم جديد"})
    assert r.status_code == 200 and r.json()["full_name"] == "اسم جديد"
