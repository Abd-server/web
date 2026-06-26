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

from fastapi import APIRouter, Depends, HTTPException, status
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
