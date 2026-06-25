"""
═══════════════════════════════════════════════════════════════
  وحدة الأمان (security.py) — محدّثة في القطعة 1-ب
═══════════════════════════════════════════════════════════════

ما الجديد عن نسخة القطعة 1-أ:
  1) الإعدادات تُقرأ من config.py (الذي يقرأ من البيئة) بدل كتابة السرّ هنا.
  2) decode_token صار يقبل expected_type للتحقق من نوع التوكن
     (يمنع استعمال refresh مكان access والعكس) — معالجة الثغرة المذكورة.

الدوال نفسها لم تتغيّر سلوكياً، فالاختبارات القديمة تبقى صالحة.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from app.core.config import settings


# للتوافق مع الكود القديم الذي يستورد AuthConfig
class AuthConfig:
    JWT_SECRET = settings.JWT_SECRET
    JWT_ALGORITHM = settings.JWT_ALGORITHM
    ACCESS_TOKEN_MINUTES = settings.ACCESS_TOKEN_MINUTES
    REFRESH_TOKEN_DAYS = settings.REFRESH_TOKEN_DAYS
    BCRYPT_ROUNDS = settings.BCRYPT_ROUNDS


# ───── كلمات المرور ─────

def hash_password(plain_password: str) -> str:
    """يجزّئ كلمة المرور بـ bcrypt مع salt عشوائي."""
    salt = bcrypt.gensalt(rounds=AuthConfig.BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """يتحقق أن كلمة المرور تطابق التجزئة المخزّنة."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


# ───── توكنات JWT ─────

def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, AuthConfig.JWT_SECRET, algorithm=AuthConfig.JWT_ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(
        user_id, timedelta(minutes=AuthConfig.ACCESS_TOKEN_MINUTES), "access"
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        user_id, timedelta(days=AuthConfig.REFRESH_TOKEN_DAYS), "refresh"
    )


def decode_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """
    يفك ويتحقق من التوكن (التوقيع + الصلاحية).
    إن مُرّر expected_type ("access" أو "refresh") يتحقق أيضاً أن النوع مطابق.
    يرجّع الحمولة لو صالحاً، أو None لو منتهياً/مزوّراً/نوعه خاطئ.
    """
    try:
        payload = jwt.decode(
            token, AuthConfig.JWT_SECRET, algorithms=[AuthConfig.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    # معالجة الثغرة: رفض التوكن لو نوعه لا يطابق المتوقّع
    if expected_type is not None and payload.get("type") != expected_type:
        return None

    return payload
