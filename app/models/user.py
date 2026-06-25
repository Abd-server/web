"""
═══════════════════════════════════════════════════════════════
  نموذج المستخدم (user.py) — القطعة 1-ب
═══════════════════════════════════════════════════════════════

جدول users في قاعدة البيانات. نخزّن password_hash فقط (ليس كلمة المرور).
عمود role يميّز المستخدم العادي عن المدير لاحقاً.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(String, default="user", nullable=False)  # user | admin
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
