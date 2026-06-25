"""
═══════════════════════════════════════════════════════════════
  الاعتماديات (deps.py) — القطعة 1-ب
═══════════════════════════════════════════════════════════════

get_current_user: تُحقّق من توكن access في ترويسة Authorization،
وتُرجع المستخدم الحالي. هذه هي البوابة التي تحمي كل مسار خاص،
وهي أساس "كل مستخدم يرى أفرانه فقط" في القطع القادمة.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.database import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauth = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="توكن غير صالح أو مفقود",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauth

    # نتحقق أن التوكن من نوع access تحديداً (يستفيد من معالجة الثغرة)
    payload = decode_token(creds.credentials, expected_type="access")
    if payload is None:
        raise unauth

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if user is None:
        raise unauth

    return user
