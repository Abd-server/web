"""
═══════════════════════════════════════════════════════════════
  مسارات الأفران (kilns.py) — محدّث للحقول الحقيقية
═══════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.device_auth import get_kiln_by_device_key
from app.core.notifications import process_reading_notifications, send_notification, log_event
from app.db.database import get_db
from app.models.user import User
from app.models.kiln import Kiln, Reading, Event, generate_device_key
from app.models.kiln_schemas import (
    KilnCreate, KilnUpdate, KilnResponse, KilnWithKeyResponse,
    ReadingIngest, ReadingResponse,
    NotifySettings, NotifySettingsResponse, StopStatusResponse,
    EventResponse,
)

router = APIRouter(tags=["الأفران"])


def _get_owned_kiln(kiln_id: str, user: User, db: Session) -> Kiln:
    kiln = (
        db.query(Kiln)
        .filter(Kiln.id == kiln_id, Kiln.owner_id == user.id)
        .first()
    )
    if kiln is None:
        raise HTTPException(status_code=404, detail="الفرن غير موجود")
    return kiln


# ═════════════ مسارات المستخدم ═════════════

@router.post("/kilns", response_model=KilnWithKeyResponse, status_code=201)
def create_kiln(body: KilnCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kiln = Kiln(owner_id=current_user.id, name=body.name, location=body.location)
    db.add(kiln); db.commit(); db.refresh(kiln)
    return kiln


@router.get("/kilns", response_model=List[KilnResponse])
def list_my_kilns(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Kiln).filter(Kiln.owner_id == current_user.id)
        .order_by(Kiln.created_at.desc()).all()
    )


@router.get("/kilns/{kiln_id}", response_model=KilnResponse)
def get_kiln(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_owned_kiln(kiln_id, current_user, db)


@router.patch("/kilns/{kiln_id}", response_model=KilnResponse)
def update_kiln(kiln_id: str, body: KilnUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kiln = _get_owned_kiln(kiln_id, current_user, db)
    for field, value in body.dict(exclude_unset=True).items():
        setattr(kiln, field, value)
    db.commit(); db.refresh(kiln)
    return kiln


@router.delete("/kilns/{kiln_id}", status_code=204)
def delete_kiln(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kiln = _get_owned_kiln(kiln_id, current_user, db)
    db.delete(kiln); db.commit()
    return None


@router.get("/kilns/{kiln_id}/readings", response_model=List[ReadingResponse])
def get_kiln_readings(kiln_id: str, limit: int = 200, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_kiln(kiln_id, current_user, db)
    limit = max(1, min(limit, 2000))
    rows = (
        db.query(Reading).filter(Reading.kiln_id == kiln_id)
        .order_by(Reading.recorded_at.desc()).limit(limit).all()
    )
    return list(reversed(rows))  # أقدم→أحدث (مناسب للرسم البياني)


@router.get("/kilns/{kiln_id}/latest", response_model=ReadingResponse)
def get_latest_reading(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_kiln(kiln_id, current_user, db)
    reading = (
        db.query(Reading).filter(Reading.kiln_id == kiln_id)
        .order_by(Reading.recorded_at.desc()).first()
    )
    if reading is None:
        raise HTTPException(status_code=404, detail="لا توجد قراءات بعد")
    return reading


@router.get("/kilns/{kiln_id}/device-key", response_model=KilnWithKeyResponse)
def get_device_key(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """يرجّع مفتاح الجهاز للمالك (يُعرض من السيرفر، فيظهر على أي متصفح/جهاز)."""
    kiln = _get_owned_kiln(kiln_id, current_user, db)
    return kiln


@router.post("/kilns/{kiln_id}/rotate-key", response_model=KilnWithKeyResponse)
def rotate_device_key(kiln_id: str, body: dict = Body(default={}), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # حماية: يجب إرسال تأكيد صريح (confirm=="تجديد") لمنع الضغط بالخطأ
    if str(body.get("confirm", "")).strip() != "تجديد":
        raise HTTPException(status_code=400, detail="يلزم تأكيد التجديد")
    kiln = _get_owned_kiln(kiln_id, current_user, db)
    kiln.device_key = generate_device_key()
    db.commit(); db.refresh(kiln)
    return kiln


# ═════════════ مسار الجهاز (الأردوينو) ═════════════

@router.post("/device/readings", response_model=ReadingResponse, status_code=201)
def ingest_reading(body: ReadingIngest, kiln: Kiln = Depends(get_kiln_by_device_key), db: Session = Depends(get_db)):
    """يستقبل قراءة من الأردوينو بكل الحقول. الفرن يُحدَّد من X-Device-Key."""
    reading = Reading(kiln_id=kiln.id, **body.dict(exclude_unset=True))
    db.add(reading); db.commit(); db.refresh(reading)
    # معالجة الإشعارات (تغيّر المرحلة، الإشعار الدوري، تجاوز الحد)
    try:
        process_reading_notifications(kiln, reading, db)
    except Exception as e:
        print(f"تنبيه: تعذّرت معالجة الإشعارات: {e}")
    return reading


# ═════════════ الإيقاف الإجباري ═════════════

@router.post("/kilns/{kiln_id}/stop", status_code=200)
def request_stop(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """المستخدم يرفع علم الإيقاف. الأردوينو يسأل عنه ويتوقف."""
    kiln = _get_owned_kiln(kiln_id, current_user, db)
    kiln.stop_requested = 1
    db.commit()
    log_event(db, kiln.id, "stop", "🛑 إيقاف إجباري",
              message="قام المستخدم بالضغط على زر الإيقاف الإجباري لإيقاف الفرن.",
              color="#ff5252", icon="🛑")
    return {"status": "ok", "message": "تم إرسال أمر الإيقاف"}


@router.get("/device/stop-status", response_model=StopStatusResponse)
def device_check_stop(kiln: Kiln = Depends(get_kiln_by_device_key), db: Session = Depends(get_db)):
    """
    الأردوينو يسأل: هل فيه أمر إيقاف؟
    نمط "الاستهلاك لمرة واحدة": لو العلم مرفوع، نرجّعه true ثم ننزّله فوراً
    في نفس اللحظة. هكذا يُسلّم الأمر مرة واحدة فقط ولا تحدث حلقة تكرار،
    دون الاعتماد على تأكيد منفصل من الأردوينو قد يفشل لأسباب شبكية.
    """
    was_requested = bool(kiln.stop_requested)
    if was_requested:
        kiln.stop_requested = 0   # ننزّل العلم فور تسليمه
        db.commit()
    return StopStatusResponse(stop_requested=was_requested)


@router.post("/device/stop-confirm", status_code=200)
def device_confirm_stop(kiln: Kiln = Depends(get_kiln_by_device_key), db: Session = Depends(get_db)):
    """الأردوينو يؤكّد أنه نفّذ التوقف؛ هنا فقط ننزّل العلم."""
    kiln.stop_requested = 0
    db.commit()
    return {"status": "ok"}


# ═════════════ إعدادات الإشعارات ═════════════

@router.get("/kilns/{kiln_id}/notify", response_model=NotifySettingsResponse)
def get_notify(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kiln = _get_owned_kiln(kiln_id, current_user, db)
    return NotifySettingsResponse(
        notify_channel=kiln.notify_channel,
        notify_enabled=bool(kiln.notify_enabled),
        notify_interval=kiln.notify_interval,
        stage_notify=bool(kiln.stage_notify),
        pushover_configured=bool(kiln.pushover_token and kiln.pushover_user),
        telegram_configured=bool(kiln.telegram_token and kiln.telegram_chat),
    )


@router.put("/kilns/{kiln_id}/notify", response_model=NotifySettingsResponse)
def set_notify(kiln_id: str, body: NotifySettings, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kiln = _get_owned_kiln(kiln_id, current_user, db)
    data = body.dict(exclude_unset=True)
    # حقول منطقية تُحوّل لأرقام
    if "notify_enabled" in data: kiln.notify_enabled = 1 if data["notify_enabled"] else 0
    if "stage_notify"   in data: kiln.stage_notify   = 1 if data["stage_notify"] else 0
    if "notify_interval" in data: kiln.notify_interval = int(data["notify_interval"])
    if "notify_channel"  in data: kiln.notify_channel  = data["notify_channel"]
    # التوكنات (تُحفظ كما هي)
    for f in ("pushover_token", "pushover_user", "telegram_token", "telegram_chat"):
        if f in data:
            setattr(kiln, f, data[f] or None)
    kiln.last_notified_temp = 0  # إعادة ضبط العدّاد عند تغيير الإعدادات
    db.commit(); db.refresh(kiln)
    return get_notify(kiln_id, current_user, db)


@router.post("/kilns/{kiln_id}/notify/test", status_code=200)
def test_notify(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kiln = _get_owned_kiln(kiln_id, current_user, db)
    sent = send_notification(kiln, "🔔 هذا إشعار تجريبي من منصة الأفران 🌡️", title="تجريبي", db=db)
    if not sent:
        raise HTTPException(status_code=400, detail="لم تُضبط توكنات القناة المختارة")
    return {"status": "ok", "message": "تم إرسال الإشعار التجريبي"}


# ═════════════ سجل الأحداث ═════════════

@router.get("/kilns/{kiln_id}/events", response_model=List[EventResponse])
def get_kiln_events(kiln_id: str, limit: int = 500, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """أحداث الفرن المهمة (الأحدث أولاً) — لصفحة سجل الأحداث."""
    _get_owned_kiln(kiln_id, current_user, db)
    limit = max(1, min(limit, 2000))
    return (
        db.query(Event).filter(Event.kiln_id == kiln_id)
        .order_by(Event.created_at.desc()).limit(limit).all()
    )


@router.get("/kilns/{kiln_id}/export.csv")
def export_readings_csv(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """تحميل كل القراءات كملف CSV (يفتح في Excel، يدعم العربي)."""
    import csv, io
    from fastapi.responses import StreamingResponse

    kiln = _get_owned_kiln(kiln_id, current_user, db)
    rows = (
        db.query(Reading).filter(Reading.kiln_id == kiln_id)
        .order_by(Reading.recorded_at.asc()).all()
    )

    H_NAMES = {0: "متوقف", 1: "المؤقت", 2: "الحرق التصاعدي", 3: "التثبيت", 4: "النزول التدريجي", 5: "انتهى"}
    columns = [
        ("recorded_at", "الوقت"), ("c1", "حرارة حقيقية"), ("i1", "حرارة افتراضية"),
        ("x", "الدرجة النهائية"), ("h", "الساعات"), ("H", "حالة البرنامج"),
        ("MARAHEL", "المراحل"), ("DOWN", "النزول التدريجي"),
        ("ElectricOff", "حالة الحساس"), ("wiresActive", "الأسلاك"),
    ]

    out = io.StringIO()
    out.write("\ufeff")  # BOM عشان Excel يقرأ العربي
    writer = csv.writer(out)
    writer.writerow([ar for (_, ar) in columns])
    for r in rows:
        row = []
        for (key, _) in columns:
            val = getattr(r, key, "")
            if key == "recorded_at" and val:
                val = val.strftime("%Y-%m-%d %H:%M:%S")
            elif key == "H":
                val = H_NAMES.get(val, val)
            elif key == "ElectricOff":
                val = "خلل" if val == 1 else "يعمل"
            elif key in ("MARAHEL", "DOWN"):
                val = "مفعّل" if val == 1 else "غير مفعّل"
            row.append("" if val is None else val)
        writer.writerow(row)

    out.seek(0)
    safe_name = (kiln.name or "kiln").replace(" ", "_")
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_readings.csv"'},
    )


@router.get("/kilns/{kiln_id}/events.csv")
def export_events_csv(kiln_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """تحميل سجل الأحداث (تحوّل المراحل، الإشعارات، الإيقاف) كملف CSV يفتح في Excel."""
    import csv, io
    from fastapi.responses import StreamingResponse
    from app.models.kiln import Event

    kiln = _get_owned_kiln(kiln_id, current_user, db)
    rows = (
        db.query(Event).filter(Event.kiln_id == kiln_id)
        .order_by(Event.created_at.asc()).all()
    )

    type_ar = {"stage": "تحوّل مرحلة", "notification": "إشعار حرارة", "stop": "إيقاف إجباري"}

    out = io.StringIO()
    out.write("\ufeff")  # BOM عشان Excel يقرأ العربي
    writer = csv.writer(out)
    writer.writerow(["الوقت", "النوع", "العنوان", "التفاصيل"])
    for ev in rows:
        t = ev.created_at.strftime("%Y-%m-%d %H:%M:%S") if ev.created_at else ""
        writer.writerow([
            t,
            type_ar.get(ev.type, ev.type),
            ev.title or "",
            ev.message or "",
        ])

    out.seek(0)
    safe_name = (kiln.name or "kiln").replace(" ", "_")
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_events.csv"'},
    )
