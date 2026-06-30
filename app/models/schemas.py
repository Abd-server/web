"""
═══════════════════════════════════════════════════════════════
  مخططات البيانات (schemas.py) — القطعة 1-ب
═══════════════════════════════════════════════════════════════

Pydantic يتحقق من شكل البيانات الداخلة والخارجة تلقائياً.
EmailStr يرفض أي بريد غير صالح قبل أن يصل للمنطق — أمان مجاني.

ملاحظة: نستخدم Optional[str] (وليس str | None) للتوافق مع Python 3.9.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="8 أحرف على الأقل")
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str]
    role: str
    created_at: datetime
    timezone: Optional[str] = "Asia/Muscat"

    class Config:
        from_attributes = True  # يسمح بالتحويل من نموذج SQLAlchemy


# ───── استرجاع وتغيير كلمة المرور ─────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ChangeNameRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=80)
