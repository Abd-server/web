"""
═══════════════════════════════════════════════════════════════
  مسارات المصادقة (auth.py) — القطعة 1-ب
═══════════════════════════════════════════════════════════════

  POST /auth/register  — إنشاء حساب جديد
  POST /auth/login     — تسجيل الدخول (يرجّع access + refresh)
  POST /auth/refresh   — تجديد access بواسطة refresh
  GET  /auth/me        — بيانات المستخدم الحالي (مسار محمي)

يستخدم security.py الموجود دون إعادة كتابته.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from app.core.deps import get_current_user
from app.core.email_service import send_reset_code
from app.db.database import get_db
from app.models.user import User
from app.models.schemas import (
    RegisterRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserResponse,
    ForgotPasswordRequest, ResetPasswordRequest,
    ChangePasswordRequest, ChangeNameRequest,
)

router = APIRouter(prefix="/auth", tags=["المصادقة"])

# المناطق الزمنية المدعومة (اسم IANA → يُعرض في القائمة بالواجهة)
VALID_TIMEZONES = {
    "Asia/Muscat", "Asia/Riyadh", "Asia/Dubai", "Asia/Kuwait", "Asia/Qatar",
    "Asia/Bahrain", "Asia/Baghdad", "Asia/Amman", "Asia/Beirut", "Asia/Jerusalem",
    "Africa/Cairo", "Asia/Tehran", "Asia/Karachi", "Asia/Kolkata", "Asia/Dhaka",
    "Asia/Istanbul", "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Moscow",
    "America/New_York", "America/Chicago", "America/Los_Angeles", "UTC",
}


@router.post("/register", response_model=UserResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email == body.email).first()
    if exists:
        raise HTTPException(status_code=409, detail="البريد مسجّل مسبقاً")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    # نفس رسالة الخطأ للحالتين (عدم وجود المستخدم / كلمة خاطئة) لمنع تخمين البريد
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="البريد أو كلمة المرور غير صحيحة")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=401, detail="توكن التجديد غير صالح")

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if user is None:
        raise HTTPException(status_code=401, detail="المستخدم غير موجود")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/me/timezone", response_model=UserResponse)
def update_timezone(body: dict = Body(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """تحديث المنطقة الزمنية للمستخدم (اسم IANA مثل Asia/Muscat)."""
    tz = str(body.get("timezone", "")).strip()
    # تحقق بسيط: نقبل فقط أسماء IANA صالحة معروفة لدينا
    if tz not in VALID_TIMEZONES:
        raise HTTPException(status_code=400, detail="منطقة زمنية غير صالحة")
    current_user.timezone = tz
    db.commit(); db.refresh(current_user)
    return current_user


# ═══════════════ استرجاع كلمة المرور ═══════════════

import secrets as _secrets
from datetime import datetime, timezone, timedelta


@router.post("/forgot-password", status_code=200)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """يرسل رمز استرجاع لإيميل المستخدم. لا يكشف إن كان الإيميل موجوداً (أمان)."""
    user = db.query(User).filter(User.email == body.email).first()
    if user:
        code = f"{_secrets.randbelow(1000000):06d}"  # 6 أرقام
        user.reset_code = code
        user.reset_expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()
        send_reset_code(user.email, code, user.full_name or "")
    # نفس الرد دائماً حتى لا يُكتشف وجود الإيميل
    return {"message": "إذا كان الإيميل مسجّلاً، سيصلك رمز الاسترجاع."}


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """يتحقق من الرمز ويعيّن كلمة مرور جديدة، ثم يسجّل الدخول مباشرة."""
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not user.reset_code:
        raise HTTPException(status_code=400, detail="رمز غير صالح")

    # تحقق من انتهاء الصلاحية
    expires = user.reset_expires
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is None or datetime.now(timezone.utc) > expires:
        raise HTTPException(status_code=400, detail="انتهت صلاحية الرمز، اطلب رمزاً جديداً")

    if body.code != user.reset_code:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح")

    # عيّن كلمة المرور الجديدة وامسح الرمز
    user.password_hash = hash_password(body.new_password)
    user.reset_code = None
    user.reset_expires = None
    db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


# ═══════════════ تغيير كلمة المرور / الاسم (من داخل الحساب) ═══════════════

@router.post("/change-password", status_code=200)
def change_password(body: ChangePasswordRequest,
                    current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """تغيير كلمة المرور مع التحقق من الحالية."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة")
    current_user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"message": "تم تغيير كلمة المرور بنجاح"}


@router.post("/change-name", response_model=UserResponse)
def change_name(body: ChangeNameRequest,
                current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """تغيير الاسم المعروض."""
    current_user.full_name = body.full_name
    db.commit()
    db.refresh(current_user)
    return current_user


# ═══════════════ ربط تيليجرام (المرحلة ب) ═══════════════

from app.core.telegram_bot import generate_link_code, handle_update
from app.core.config import settings as _settings
from fastapi import Request


@router.post("/telegram/link-code", status_code=200)
def create_telegram_link_code(current_user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    """ينشئ رمز ربط مؤقت يعرضه الموقع للعميل لإرساله للبوت."""
    if not _settings.telegram_configured():
        raise HTTPException(status_code=503, detail="بوت تيليجرام غير مُهيّأ على الخادم")
    code = generate_link_code(current_user, db)
    return {"code": code, "expires_minutes": 10, "bot_username": "KilnMonitor_bot"}


@router.get("/telegram/status", status_code=200)
def telegram_status(current_user: User = Depends(get_current_user)):
    """يخبر الواجهة هل الحساب مربوط بتيليجرام."""
    return {"linked": bool(current_user.telegram_chat)}


@router.post("/telegram/unlink", status_code=200)
def telegram_unlink(current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """يلغي الربط بتيليجرام."""
    current_user.telegram_chat = None
    current_user.telegram_link_code = None
    current_user.telegram_link_expires = None
    db.commit()
    return {"message": "تم إلغاء ربط تيليجرام"}


@router.post("/telegram/webhook/{secret}", include_in_schema=False)
async def telegram_webhook(secret: str, request: Request,
                           db: Session = Depends(get_db)):
    """
    نقطة استقبال رسائل البوت من تيليجرام.
    الرابط يحتوي على سرّ (= التوكن) لمنع العبث من الخارج.
    """
    if secret != _settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        update = await request.json()
        handle_update(update, db)
    except Exception as e:
        print(f"❌ خطأ webhook تيليجرام: {e}")
    return {"ok": True}


# ═══════════════ ربط ntfy (قناة بديلة تفتح بالخليج) ═══════════════

import secrets as _secrets


@router.post("/ntfy/link", status_code=200)
def create_ntfy_topic(current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """
    يفعّل ntfy ويرجّع موضوع العميل.
    الموضوع يُولّد مرة واحدة ويبقى ثابتاً مدى الحياة (لا يتغيّر مع الإلغاء/إعادة الربط).
    """
    if not current_user.ntfy_topic:
        current_user.ntfy_topic = "furanfakhar-" + _secrets.token_hex(8)
    current_user.ntfy_enabled = True
    db.commit()
    return {
        "topic": current_user.ntfy_topic,
        "url": f"https://ntfy.sh/{current_user.ntfy_topic}",
    }


@router.get("/ntfy/status", status_code=200)
def ntfy_status(current_user: User = Depends(get_current_user)):
    """يخبر الواجهة هل ntfy مفعّل، مع الموضوع الثابت."""
    return {"linked": bool(current_user.ntfy_enabled),
            "topic": current_user.ntfy_topic or ""}


@router.post("/ntfy/unlink", status_code=200)
def ntfy_unlink(current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """يوقف إشعارات ntfy دون مسح الموضوع (يبقى ثابتاً للمستقبل)."""
    current_user.ntfy_enabled = False
    db.commit()
    return {"message": "تم إيقاف إشعارات ntfy"}
