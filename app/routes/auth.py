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
from app.db.database import get_db
from app.models.user import User
from app.models.schemas import (
    RegisterRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserResponse,
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
