"""
═══════════════════════════════════════════════════════════════
  مخططات الأفران (kiln_schemas.py) — محدّث للحقول الحقيقية
═══════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ───── الأفران ─────

class KilnCreate(BaseModel):
    name: str = Field(min_length=1)
    location: Optional[str] = None


class KilnUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None


class KilnResponse(BaseModel):
    id: str
    name: str
    location: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True


class KilnWithKeyResponse(KilnResponse):
    device_key: str


# ───── القراءات ─────
# كل الحقول اختيارية: الأردوينو قد يرسل بعضها فقط.

class ReadingIngest(BaseModel):
    c1: Optional[float] = None
    i1: Optional[float] = None
    x:  Optional[float] = None
    H:  Optional[int]   = None
    h:  Optional[float] = None
    t:  Optional[float] = None
    D:  Optional[float] = None
    mD: Optional[float] = None
    ht: Optional[float] = None
    mt: Optional[float] = None
    m:  Optional[float] = None
    x1: Optional[float] = None; t1: Optional[float] = None
    x2: Optional[float] = None; t2: Optional[float] = None
    x3: Optional[float] = None; t3: Optional[float] = None
    MARAHEL:     Optional[int] = None
    DOWN:        Optional[int] = None
    ElectricOff: Optional[int] = None
    wiresActive: Optional[str] = None

    class Config:
        extra = "ignore"  # تجاهل أي حقل إضافي بدل رفض الطلب


class ReadingResponse(BaseModel):
    id: str
    kiln_id: str
    c1: Optional[float]; i1: Optional[float]; x: Optional[float]
    H: Optional[int]; h: Optional[float]; t: Optional[float]
    D: Optional[float]; mD: Optional[float]
    ht: Optional[float]; mt: Optional[float]; m: Optional[float] = None
    x1: Optional[float]; t1: Optional[float]
    x2: Optional[float]; t2: Optional[float]
    x3: Optional[float]; t3: Optional[float]
    MARAHEL: Optional[int]; DOWN: Optional[int]
    ElectricOff: Optional[int]; wiresActive: Optional[str]
    recorded_at: datetime
    class Config:
        from_attributes = True


# ───── إعدادات الإشعارات ─────

class NotifySettings(BaseModel):
    notify_channel:  Optional[str]  = None   # pushover|telegram
    notify_enabled:  Optional[bool] = None
    notify_interval: Optional[int]  = None
    stage_notify:    Optional[bool] = None
    pushover_token:  Optional[str]  = None
    pushover_user:   Optional[str]  = None
    telegram_token:  Optional[str]  = None
    telegram_chat:   Optional[str]  = None


class NotifySettingsResponse(BaseModel):
    """لا نُرجع التوكنات كاملة، فقط نخبر هل هي مضبوطة."""
    notify_channel: str
    notify_enabled: bool
    notify_interval: int
    stage_notify: bool
    pushover_configured: bool
    telegram_configured: bool


class StopStatusResponse(BaseModel):
    stop_requested: bool


class EventResponse(BaseModel):
    id: str
    type: str
    title: str
    message: Optional[str]
    color: str
    icon: str
    created_at: datetime
    class Config:
        from_attributes = True
