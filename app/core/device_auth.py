"""
═══════════════════════════════════════════════════════════════
  مصادقة الجهاز (device_auth.py) — القطعة 1-ج
═══════════════════════════════════════════════════════════════

الأردوينو لا يملك حساباً ولا كلمة مرور. بدلاً من ذلك يرسل مفتاحه
الفريد في ترويسة X-Device-Key. هذه الدالة تتحقق من المفتاح
وتُرجع الفرن المطابق له.

هذا يفصل تماماً بين:
  • المستخدم (يدخل بـ JWT)  → يقرأ بياناته
  • الجهاز (يرسل بـ device_key) → يكتب القراءات
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.kiln import Kiln


def get_kiln_by_device_key(
    x_device_key: str = Header(default=None, alias="X-Device-Key"),
    db: Session = Depends(get_db),
) -> Kiln:
    if not x_device_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="مفتاح الجهاز مفقود (X-Device-Key)",
        )
    kiln = db.query(Kiln).filter(Kiln.device_key == x_device_key).first()
    if kiln is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="مفتاح الجهاز غير صالح",
        )
    return kiln
