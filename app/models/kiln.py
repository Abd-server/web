"""
═══════════════════════════════════════════════════════════════
  نموذج الفرن والقراءات (kiln.py)
═══════════════════════════════════════════════════════════════

ملاحظة مهمة عن SQLite:
  SQLite لا يفرّق بين الحروف الكبيرة والصغيرة في أسماء الأعمدة،
  فـ H و h يُعتبران نفس العمود. لذلك نعطي كل عمود اسم تخزين فعلياً
  فريداً (العمود الأول في Column(...)) بينما نُبقي اسم الخاصية في
  بايثون مطابقاً لما يرسله الأردوينو. هكذا:
    - الأردوينو يرسل: c1, i1, x, H, h, D, mD ...
    - قاعدة البيانات تخزّن: ..., prog_state, hours, hold_dur, hold_now ...
"""
from __future__ import annotations

import uuid
import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, Index
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def generate_device_key() -> str:
    return "dvk_" + secrets.token_urlsafe(24)


class Kiln(Base):
    __tablename__ = "kilns"

    id = Column(String, primary_key=True, default=_uuid)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    device_key = Column(String, unique=True, index=True, default=generate_device_key)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    stop_requested = Column(Integer, default=0, nullable=False)

    notify_channel  = Column(String, default="pushover", nullable=False)
    notify_enabled  = Column(Integer, default=1, nullable=False)
    notify_interval = Column(Integer, default=100, nullable=False)
    stage_notify    = Column(Integer, default=1, nullable=False)
    pushover_token  = Column(String, nullable=True)
    pushover_user   = Column(String, nullable=True)
    telegram_token  = Column(String, nullable=True)
    telegram_chat   = Column(String, nullable=True)
    last_notified_temp = Column(Float, default=0, nullable=False)
    last_stage         = Column(Integer, default=-1, nullable=False)
    was_online         = Column(Integer, default=-1, nullable=False)  # -1 مجهول، 1 متصل، 0 منقطع
    tg_link_code       = Column(String, nullable=True)   # رمز ربط تيليجرام مؤقت للفرن
    tg_link_expires    = Column(DateTime, nullable=True)

    readings = relationship(
        "Reading", back_populates="kiln", cascade="all, delete-orphan"
    )


class Reading(Base):
    __tablename__ = "readings"

    id = Column(String, primary_key=True, default=_uuid)
    kiln_id = Column(String, ForeignKey("kilns.id"), nullable=False, index=True)

    # خاصية_بايثون = Column("اسم_العمود_الفعلي_الفريد", ...)
    c1 = Column("c1", Float, nullable=True)   # الحرارة الحقيقية
    i1 = Column("i1", Float, nullable=True)   # الافتراضية
    x  = Column("final_temp", Float, nullable=True)   # الدرجة النهائية

    H  = Column("prog_state", Integer, nullable=True)  # حالة البرنامج
    h  = Column("hours", Float, nullable=True)         # الساعات الجارية
    t  = Column("stage_time", Float, nullable=True)    # وقت المرحلة
    D  = Column("hold_dur", Float, nullable=True)      # مدة التثبيت
    mD = Column("hold_now", Float, nullable=True)      # دقائق التثبيت الجارية
    ht = Column("rem_hours", Float, nullable=True)     # ساعات متبقية
    mt = Column("rem_mins", Float, nullable=True)      # دقائق متبقية
    m  = Column("burn_mins_now", Float, nullable=True) # دقائق الحرق الجارية

    x1 = Column("stage1_temp", Float, nullable=True); t1 = Column("stage1_time", Float, nullable=True)
    x2 = Column("stage2_temp", Float, nullable=True); t2 = Column("stage2_time", Float, nullable=True)
    x3 = Column("stage3_temp", Float, nullable=True); t3 = Column("stage3_time", Float, nullable=True)

    MARAHEL     = Column("stages_on", Integer, nullable=True)
    DOWN        = Column("gradual_down", Integer, nullable=True)
    ElectricOff = Column("sensor_fault", Integer, nullable=True)
    wiresActive = Column("wires_active", String, nullable=True)

    recorded_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    kiln = relationship("Kiln", back_populates="readings")


Index("ix_readings_kiln_time", Reading.kiln_id, Reading.recorded_at)


class Event(Base):
    """حدث مهم في حياة الفرن (تغيّر مرحلة، إشعار، إيقاف إجباري...)."""
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=_uuid)
    kiln_id = Column(String, ForeignKey("kilns.id"), nullable=False, index=True)
    type    = Column(String, nullable=False)   # stage | notification | stop
    title   = Column(String, nullable=False)
    message = Column(String, nullable=True)
    color   = Column(String, default="#9e9e9e")
    icon    = Column(String, default="•")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )


Index("ix_events_kiln_time", Event.kiln_id, Event.created_at)


class TelegramSubscriber(Base):
    """مشترك تيليجرام لفرن معيّن — يسمح بوصول إشعارات الفرن الواحد لعدة أشخاص."""
    __tablename__ = "telegram_subscribers"

    id = Column(String, primary_key=True, default=_uuid)
    kiln_id = Column(String, ForeignKey("kilns.id"), nullable=False, index=True)
    chat_id = Column(String, nullable=False)          # معرّف محادثة تيليجرام
    name = Column(String, nullable=True)               # اسم المشترك (من تيليجرام)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


Index("ix_tgsub_kiln", TelegramSubscriber.kiln_id, TelegramSubscriber.chat_id)
