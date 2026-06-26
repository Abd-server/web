"""
اختبارات الأفران — القطعة 1-ج.
التشغيل:  pytest tests/test_kilns.py -v
الأهم: اختبار العزل (مستخدم لا يرى أفران غيره).
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./_test_kilns.db"

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


def _make_user(email, pw="password123"):
    """ينشئ مستخدماً ويرجّع ترويسة Authorization جاهزة."""
    client.post("/auth/register", json={"email": email, "password": pw})
    tok = client.post("/auth/login", json={"email": email, "password": pw}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_create_kiln_returns_device_key():
    h = _make_user("a@b.com")
    r = client.post("/kilns", json={"name": "فرن أ"}, headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "فرن أ"
    assert body["device_key"].startswith("dvk_")  # المفتاح يظهر مرة واحدة


def test_list_only_my_kilns():
    h = _make_user("a@b.com")
    client.post("/kilns", json={"name": "فرن 1"}, headers=h)
    client.post("/kilns", json={"name": "فرن 2"}, headers=h)
    r = client.get("/kilns", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_user_cannot_see_others_kilns():
    """أهم اختبار: العزل بين المستخدمين."""
    ha = _make_user("a@b.com")
    hb = _make_user("b@b.com")
    # المستخدم أ ينشئ فرناً
    kiln_a = client.post("/kilns", json={"name": "فرن أ"}, headers=ha).json()
    # المستخدم ب لا يراه في قائمته
    assert client.get("/kilns", headers=hb).json() == []
    # والمستخدم ب لا يستطيع الوصول له مباشرة (404)
    assert client.get(f"/kilns/{kiln_a['id']}", headers=hb).status_code == 404
    # ولا حذفه
    assert client.delete(f"/kilns/{kiln_a['id']}", headers=hb).status_code == 404


def test_kilns_require_auth():
    assert client.get("/kilns").status_code == 401
    assert client.post("/kilns", json={"name": "x"}).status_code == 401


def test_update_kiln():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "قديم"}, headers=h).json()
    r = client.patch(f"/kilns/{k['id']}", json={"name": "جديد"}, headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "جديد"


def test_delete_kiln():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "للحذف"}, headers=h).json()
    assert client.delete(f"/kilns/{k['id']}", headers=h).status_code == 204
    assert client.get("/kilns", headers=h).json() == []


# ───── قراءات الأردوينو ─────

def test_device_can_send_reading():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    dk = k["device_key"]
    r = client.post("/device/readings",
                    json={"c1": 845.5, "H": 2, "wiresActive": "تضخ"},
                    headers={"X-Device-Key": dk})
    assert r.status_code == 201
    assert r.json()["c1"] == 845.5


def test_device_bad_key_rejected():
    r = client.post("/device/readings", json={"c1": 100},
                    headers={"X-Device-Key": "dvk_wrong"})
    assert r.status_code == 401


def test_device_missing_key_rejected():
    r = client.post("/device/readings", json={"c1": 100})
    assert r.status_code == 401


def test_owner_sees_readings_others_dont():
    ha = _make_user("a@b.com")
    hb = _make_user("b@b.com")
    k = client.post("/kilns", json={"name": "فرن أ"}, headers=ha).json()
    client.post("/device/readings", json={"c1": 500, "H": 1},
                headers={"X-Device-Key": k["device_key"]})
    # المالك يرى القراءة
    r = client.get(f"/kilns/{k['id']}/readings", headers=ha)
    assert r.status_code == 200 and len(r.json()) == 1
    # غير المالك لا يصل أصلاً (404)
    assert client.get(f"/kilns/{k['id']}/readings", headers=hb).status_code == 404


def test_latest_reading():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    dk = {"X-Device-Key": k["device_key"]}
    client.post("/device/readings", json={"c1": 100}, headers=dk)
    client.post("/device/readings", json={"c1": 200}, headers=dk)
    r = client.get(f"/kilns/{k['id']}/latest", headers=h)
    assert r.status_code == 200
    assert r.json()["c1"] == 200  # الأحدث


def test_rotate_key_invalidates_old():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    old_key = k["device_key"]
    new = client.post(f"/kilns/{k['id']}/rotate-key", headers=h).json()
    assert new["device_key"] != old_key
    # المفتاح القديم ما عاد يشتغل
    r = client.post("/device/readings", json={"c1": 1},
                    headers={"X-Device-Key": old_key})
    assert r.status_code == 401


# ───── الإيقاف الإجباري ─────

def test_stop_flag_flow():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    dk = {"X-Device-Key": k["device_key"]}
    # في البداية لا يوجد أمر إيقاف
    r = client.get("/device/stop-status", headers=dk)
    assert r.status_code == 200 and r.json()["stop_requested"] is False
    # المستخدم يطلب الإيقاف
    assert client.post(f"/kilns/{k['id']}/stop", headers=h).status_code == 200
    # الأردوينو يسأل: يجد الأمر — ويبقى مرفوعاً مهما تكرر السؤال
    assert client.get("/device/stop-status", headers=dk).json()["stop_requested"] is True
    assert client.get("/device/stop-status", headers=dk).json()["stop_requested"] is True
    # لا ينزل إلا بعد أن يؤكّد الأردوينو التنفيذ
    assert client.post("/device/stop-confirm", headers=dk).status_code == 200
    assert client.get("/device/stop-status", headers=dk).json()["stop_requested"] is False



def test_stop_requires_ownership():
    ha = _make_user("a@b.com")
    hb = _make_user("b@b.com")
    k = client.post("/kilns", json={"name": "فرن أ"}, headers=ha).json()
    # ب لا يستطيع إيقاف فرن أ
    assert client.post(f"/kilns/{k['id']}/stop", headers=hb).status_code == 404


# ───── إعدادات الإشعارات ─────

def test_notify_settings_default_and_update():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    # الافتراضي
    r = client.get(f"/kilns/{k['id']}/notify", headers=h)
    assert r.status_code == 200
    s = r.json()
    assert s["notify_channel"] == "pushover"
    assert s["pushover_configured"] is False
    # تحديث
    r = client.put(f"/kilns/{k['id']}/notify", headers=h, json={
        "notify_channel": "telegram", "notify_interval": 50,
        "telegram_token": "123:ABC", "telegram_chat": "999",
    })
    assert r.status_code == 200
    s = r.json()
    assert s["notify_channel"] == "telegram"
    assert s["notify_interval"] == 50
    assert s["telegram_configured"] is True
    # التوكن لا يُكشف في الرد
    assert "telegram_token" not in s


def test_notify_settings_isolated():
    ha = _make_user("a@b.com")
    hb = _make_user("b@b.com")
    k = client.post("/kilns", json={"name": "فرن أ"}, headers=ha).json()
    assert client.get(f"/kilns/{k['id']}/notify", headers=hb).status_code == 404


def test_test_notify_without_tokens_fails():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    # بدون توكنات يفشل بـ 400
    assert client.post(f"/kilns/{k['id']}/notify/test", headers=h).status_code == 400


# ───── سجل الأحداث ─────

def test_stop_creates_event():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    client.post(f"/kilns/{k['id']}/stop", headers=h)
    r = client.get(f"/kilns/{k['id']}/events", headers=h)
    assert r.status_code == 200
    events = r.json()
    assert any(e["type"] == "stop" for e in events)


def test_stage_change_creates_event():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    dk = {"X-Device-Key": k["device_key"]}
    # أول قراءة تضبط المرحلة (لا حدث), الثانية تغيّرها (حدث)
    client.post("/device/readings", json={"c1": 100, "H": 1}, headers=dk)
    client.post("/device/readings", json={"c1": 200, "H": 2}, headers=dk)
    r = client.get(f"/kilns/{k['id']}/events", headers=h)
    events = r.json()
    assert any(e["type"] == "stage" for e in events)


def test_events_isolated_between_users():
    ha = _make_user("a@b.com")
    hb = _make_user("b@b.com")
    k = client.post("/kilns", json={"name": "فرن أ"}, headers=ha).json()
    client.post(f"/kilns/{k['id']}/stop", headers=ha)
    # ب لا يصل لأحداث فرن أ
    assert client.get(f"/kilns/{k['id']}/events", headers=hb).status_code == 404


def test_csv_export_works():
    h = _make_user("a@b.com")
    k = client.post("/kilns", json={"name": "فرن"}, headers=h).json()
    dk = {"X-Device-Key": k["device_key"]}
    client.post("/device/readings", json={"c1": 845.5, "H": 2}, headers=dk)
    r = client.get(f"/kilns/{k['id']}/export.csv", headers=h)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "حرارة حقيقية" in r.text  # رأس عربي موجود
