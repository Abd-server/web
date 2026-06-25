"""
═══════════════════════════════════════════════════════════════
  التطبيق الرئيسي (main.py) — القطعة 2 (مع الواجهة)
═══════════════════════════════════════════════════════════════

التشغيل:
    uvicorn app.main:app --reload --port 8000

الصفحات:
    http://localhost:8000/        ← صفحة الدخول/التسجيل
    http://localhost:8000/app     ← التطبيق (أفراني + لوحات التحكم)
    http://localhost:8000/docs    ← توثيق الـ API التفاعلي
"""
from __future__ import annotations

import os
import warnings
from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.core.config import settings
from app.db.database import init_db
from app.routes import auth, kilns

app = FastAPI(title="منصة الأفران — API", version="1.0.0")
app.include_router(auth.router)
app.include_router(kilns.router)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.on_event("startup")
def _startup():
    init_db()
    if not settings.is_production_ready():
        warnings.warn(
            "تحذير أمني: JWT_SECRET ما زال القيمة المؤقتة. "
            "ضع سرّاً حقيقياً في .env قبل النشر."
        )


# ───── صفحات الواجهة ─────

@app.get("/", include_in_schema=False)
def login_page():
    """صفحة الدخول/التسجيل."""
    return FileResponse(os.path.join(_STATIC_DIR, "login.html"))


@app.get("/app", include_in_schema=False)
def app_page():
    """التطبيق: قائمة الأفران ولوحات التحكم."""
    return FileResponse(os.path.join(_STATIC_DIR, "app.html"))


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "message": "منصة الأفران تعمل"}
