"""
═══════════════════════════════════════════════════════════════
  الإشعارات (notifications.py) — القطعة 2+
═══════════════════════════════════════════════════════════════

يرسل إشعارات Pushover/Telegram باستخدام توكنات المستخدم نفسه
(المخزّنة في الفرن). يُستدعى تلقائياً عند استقبال قراءة جديدة.

ملاحظة: يستخدم urllib من المكتبة القياسية (لا حاجة لمكتبات إضافية).
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse

from app.core.config import settings

H_NAMES = {
    0: "متوقف - في انتظار الإعدادات",
    1: "المؤقت",
    2: "الحرق التصاعدي",
    3: "التثبيت",
    4: "النزول التدريجي",
    5: "البرنامج انتهى",
}

# لون وأيقونة مميزة لكل مرحلة (تظهر في السجل والإشعارات)
H_STYLE = {
    0: ("#9e9e9e", "⏸️"),   # متوقف — رمادي
    1: ("#42a5f5", "⏱️"),   # المؤقت — أزرق
    2: ("#ff7043", "🔥"),   # الحرق التصاعدي — برتقالي
    3: ("#ef5350", "🌡️"),   # التثبيت — أحمر
    4: ("#26c6da", "❄️"),   # النزول التدريجي — سماوي
    5: ("#66bb6a", "✅"),   # البرنامج انتهى — أخضر
}


def _stage_style(H):
    """يرجّع (لون، أيقونة) للمرحلة، مع قيمة افتراضية آمنة."""
    return H_STYLE.get(H, ("#ff7043", "🔥"))


def _send_ntfy(topic: str, message: str, title: str = "Kiln Monitor") -> None:
    """
    يرسل إشعاراً عبر ntfy.sh إلى موضوع العميل.
    العربية لا تُدعم في ترويسة Title، لذا نضع العنوان داخل نص الإشعار نفسه.
    """
    try:
        body = f"{title}\n{message}".encode("utf-8")
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=body,
            headers={"Tags": "fire"},  # أيقونة 🔥 بجانب الإشعار
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"❌ خطأ ntfy: {e}")


def _send_pushover(token: str, user: str, message: str, title: str = "Kiln Monitor") -> None:
    try:
        data = urllib.parse.urlencode({
            "token": token, "user": user, "message": message, "title": title,
        }).encode()
        req = urllib.request.Request("https://api.pushover.net/1/messages.json", data=data)
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"❌ خطأ Pushover: {e}")


def _send_telegram(token: str, chat_id: str, message: str) -> None:
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id, "text": message, "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"❌ خطأ تلجرام: {e}")


def _owner_telegram_chat(kiln, db=None) -> str | None:
    """يجلب chat_id الخاص بمالك الفرن (الربط على مستوى الحساب)."""
    # 1) لو الفرن نفسه فيه chat (ربط قديم) نستخدمه
    if getattr(kiln, "telegram_chat", None):
        return kiln.telegram_chat
    # 2) غير ذلك نجلب chat الخاص بصاحب الفرن
    try:
        from app.models.user import User
        from app.db.database import SessionLocal
        own_db = db or SessionLocal()
        owner = own_db.query(User).filter(User.id == kiln.owner_id).first()
        chat = owner.telegram_chat if owner else None
        if db is None:
            own_db.close()
        return chat
    except Exception as e:
        print(f"❌ خطأ جلب chat المالك: {e}")
        return None


def _owner_ntfy_topic(kiln, db=None) -> str | None:
    """يجلب موضوع ntfy الخاص بمالك الفرن، فقط إن كان مفعّلاً."""
    try:
        from app.models.user import User
        from app.db.database import SessionLocal
        own_db = db or SessionLocal()
        owner = own_db.query(User).filter(User.id == kiln.owner_id).first()
        # نرسل فقط لو الموضوع موجود والربط مفعّل
        topic = None
        if owner and owner.ntfy_topic and getattr(owner, "ntfy_enabled", False):
            topic = owner.ntfy_topic
        if db is None:
            own_db.close()
        return topic
    except Exception as e:
        print(f"❌ خطأ جلب موضوع ntfy المالك: {e}")
        return None


def _kiln_color_emoji(kiln) -> str:
    """
    يعطي كل فرن كرة ملونة ثابتة تميّزه عن باقي أفران العميل.
    اللون مشتق من معرّف الفرن (id) فيبقى ثابتاً مدى الحياة،
    ولا يتغيّر حتى لو حُذف فرن آخر.
    """
    balls = ["🔴", "🟢", "🔵", "🟡", "🟣", "🟠", "🟤", "⚪"]
    kid = str(getattr(kiln, "id", "") or "")
    if not kid:
        return "🔥"
    # مجموع رموز المعرّف يحدد اللون (توزيع ثابت ومتساوٍ)
    idx = sum(ord(c) for c in kid) % len(balls)
    return balls[idx]


def send_notification(kiln, message: str, title: str = "Kiln Monitor", db=None) -> bool:
    """يرسل عبر القناة المختارة لهذا الفرن. يرجّع True لو حاول الإرسال."""
    # نضيف اسم الفرن + كرة لونه المميزة ليفرّق العميل بين أفرانه المتعددة
    kiln_name = (getattr(kiln, "name", None) or "").strip()
    color = _kiln_color_emoji(kiln)
    if kiln_name:
        full_title = f"{color} {kiln_name} — {title}"
    else:
        full_title = f"{color} {title}"

    # طابع زمني أنيق بمنطقة العميل يُذيّل كل إشعار
    try:
        from datetime import datetime, timezone as _tz
        from zoneinfo import ZoneInfo
        tz_name = _owner_timezone(kiln, db) if db else "Asia/Muscat"
        now = datetime.now(_tz.utc).astimezone(ZoneInfo(tz_name))
        days = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
        day_ar = days[now.weekday()]
        hour = now.hour
        period = "صباحاً" if hour < 12 else "مساءً"
        h12 = hour % 12 or 12
        stamp = f"🗓️ {day_ar} · {now.day}/{now.month} · {h12}:{now.minute:02d} {period}"
        message = f"{message}\n\n{stamp}"
    except Exception:
        pass

    if kiln.notify_channel == "telegram":
        # البوت المركزي (المرحلة ب): توكن واحد + chat صاحب الفرن
        chat = _owner_telegram_chat(kiln, db)
        if settings.telegram_configured() and chat:
            _send_telegram(settings.TELEGRAM_BOT_TOKEN, chat, f"<b>{full_title}</b>\n{message}")
            return True
        # توافق خلفي: لو الفرن فيه توكن خاص قديم
        if kiln.telegram_token and kiln.telegram_chat:
            _send_telegram(kiln.telegram_token, kiln.telegram_chat, f"<b>{full_title}</b>\n{message}")
            return True
    elif kiln.notify_channel == "ntfy":
        topic = _owner_ntfy_topic(kiln, db)
        if topic:
            _send_ntfy(topic, message, full_title)
            return True
    else:
        if kiln.pushover_token and kiln.pushover_user:
            _send_pushover(kiln.pushover_token, kiln.pushover_user, message, full_title)
            return True
    return False


def _fmt_hm(total_minutes):
    """يحوّل دقائق إلى نص 'X ساعة و Y دقيقة'."""
    total_minutes = int(round(total_minutes))
    h = total_minutes // 60
    m = total_minutes % 60
    if h > 0 and m > 0:
        return f"{h} ساعة و{m} دقيقة"
    if h > 0:
        return f"{h} ساعة"
    return f"{m} دقيقة"


def _clock_after(minutes_from_now, tz_name):
    """يرجّع وقت الساعة بعد إضافة دقائق للوقت الحالي بمنطقة العميل، صيغة 12-ساعة عربية."""
    from datetime import datetime, timezone as _tz, timedelta
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(_tz.utc).astimezone(ZoneInfo(tz_name))
    except Exception:
        now = datetime.utcnow() + timedelta(hours=4)  # احتياطي عُمان
    target = now + timedelta(minutes=minutes_from_now)
    hour = target.hour
    period = "صباحاً" if hour < 12 else "مساءً"
    h12 = hour % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{target.minute:02d} {period}"


def _extra_minutes_above_1000(final_temp):
    """الوقت الإضافي بالدقائق للحرارة فوق 1000 (المعادلة: (x-1000)/0.0231 ثانية)."""
    if final_temp is None or final_temp <= 1000:
        return 0
    seconds = (final_temp - 1000) / 0.0231
    return seconds / 60.0


def _gradual_down_minutes(final_temp):
    """مدة النزول التدريجي بالدقائق: (x-200)/0.036111 ثانية."""
    if final_temp is None or final_temp <= 200:
        return 0
    seconds = (final_temp - 200) / 0.036111
    return seconds / 60.0


def _build_firing_message(reading, tz_name, offset_min=0):
    """يبني نص إشعار الحرق التصاعدي المفصّل. offset_min: دقائق تُضاف قبل بدء الحرق (للمؤقت)."""
    r = reading
    stages_on = (r.MARAHEL == 1)
    down_on = (r.DOWN == 1)
    lines = []

    lines.append(f"🌡️ حرارة بداية التشغيل (الفعلية): {int(r.c1 or 0)}°")
    lines.append(f"📊 الحرارة الافتراضية عند البداية: {int(r.i1 or 0)}°")

    if not stages_on:
        # بدون مراحل
        lines.append(f"🎯 الدرجة النهائية: {int(r.x or 0)}°")
        base_min = (r.t or 0) * 60   # وقت المرحلة الواحدة بالساعات → دقائق
        lines.append(f"⏱️ عدد ساعات الحرقة: {_fmt_hm(base_min)}")
        total_min = base_min
    else:
        # مع مراحل
        lines.append("🔷 المراحل: مفعّلة")
        lines.append(f"  • المرحلة 1: {int(r.x1 or 0)}° خلال {_fmt_hm((r.t1 or 0)*60)}")
        lines.append(f"  • المرحلة 2: {int(r.x2 or 0)}° خلال {_fmt_hm((r.t2 or 0)*60)}")
        lines.append(f"  • المرحلة 3: {int(r.x3 or 0)}° خلال {_fmt_hm((r.t3 or 0)*60)}")
        lines.append(f"🎯 الدرجة النهائية: {int(r.x or 0)}°")
        stages_min = ((r.t1 or 0) + (r.t2 or 0) + (r.t3 or 0)) * 60
        extra_min = _extra_minutes_above_1000(r.x)   # الوقت الإضافي فوق 1000 (مع المراحل فقط)
        total_min = stages_min + extra_min
        if extra_min > 0:
            lines.append(f"⏱️ زمن الحرق الكلي: {_fmt_hm(total_min)} (منها {_fmt_hm(extra_min)} للحرارة فوق 1000°)")
        else:
            lines.append(f"⏱️ زمن الحرق الكلي: {_fmt_hm(total_min)}")

    lines.append(f"🔻 النزول التدريجي: {'مفعّل' if down_on else 'غير مفعّل'}")
    lines.append(f"🧱 مدة التثبيت: {int(r.D)} دقيقة" if r.D else "🧱 مدة التثبيت: —")
    lines.append(f"🕐 الوقت المتوقع لانتهاء الحرقة: {_clock_after(offset_min + total_min, tz_name)}")

    # عند تفعيل النزول التدريجي: نضيف وقت انتهاء النزول (بعد الحرق)
    if down_on:
        down_min = _gradual_down_minutes(r.x)
        total_with_down = total_min + down_min
        lines.append(
            f"❄️ ومع النزول التدريجي (يستغرق {_fmt_hm(down_min)})، "
            f"ينتهي كل شيء الساعة: {_clock_after(offset_min + total_with_down, tz_name)}"
        )

    return "\n".join(lines)


def _build_timer_message(reading, tz_name):
    """يبني نص إشعار المؤقت: كل تفاصيل الحرق + الوقت المتبقي للتشغيل."""
    r = reading
    # الوقت المتبقي للتشغيل
    rem_min = (r.ht or 0) * 60 + (r.mt or 0)
    lines = []
    lines.append(f"⏳ المتبقي لبدء التشغIل: {_fmt_hm(rem_min)}")
    lines.append(f"🕐 الوقت المتوقع لبدء الحرق: {_clock_after(rem_min, tz_name)}")
    lines.append("")
    lines.append("— تفاصيل الحرقة القادمة —")
    # نعيد استخدام بناء الحرق، مع إزاحة = الوقت المتبقي (فيبدأ حساب الانتهاء بعد التشغيل)
    firing = _build_firing_message(reading, tz_name, offset_min=rem_min)
    lines.append(firing)
    return "\n".join(lines)


def _owner_timezone(kiln, db):
    """يجلب المنطقة الزمنية لمالك الفرن."""
    try:
        from app.models.user import User
        owner = db.query(User).filter(User.id == kiln.owner_id).first()
        if owner and owner.timezone:
            return owner.timezone
    except Exception:
        pass
    return "Asia/Muscat"


def process_reading_notifications(kiln, reading, db) -> None:
    """
    يفحص القراءة الجديدة ويرسل الإشعارات المناسبة، محدّثاً حالة الفرن.
    يُستدعى داخل مسار استقبال القراءة.
    """
    changed = False

    # 1) إشعار تغيّر المرحلة
    H = reading.H
    stage_color, stage_icon = _stage_style(H)
    if kiln.stage_notify and H is not None and H != kiln.last_stage and kiln.last_stage != -1:
        stage_name = H_NAMES.get(H, "--")
        tz_name = _owner_timezone(kiln, db)
        if H == 2:
            # الحرق التصاعدي — رسالة مفصّلة بالحسابات
            detail = _build_firing_message(reading, tz_name)
            send_notification(kiln, f"{stage_icon} بدأ الحرق التصاعدي\n\n{detail}", title="بدء الحرق التصاعدي", db=db)
        elif H == 1:
            # المؤقت — تفاصيل + الوقت المتبقي
            detail = _build_timer_message(reading, tz_name)
            send_notification(kiln, f"{stage_icon} المؤقت قيد التشغيل\n\n{detail}", title="المؤقت", db=db)
        else:
            send_notification(kiln, f"{stage_icon} تحوّل البرنامج إلى: {stage_name}", title="تحوّل المرحلة", db=db)
    if H is not None and H != kiln.last_stage:
        if kiln.last_stage != -1:
            # نسجّل الحدث في الأرشيف بلون وأيقونة المرحلة (حتى لو الإشعار معطّل)
            log_event(db, kiln.id, "stage", f"{stage_icon} المرحلة: {H_NAMES.get(H, '--')}",
                      message=f"تحوّل البرنامج إلى مرحلة: {H_NAMES.get(H, '--')}",
                      color=stage_color, icon=stage_icon)
        kiln.last_stage = H
        changed = True

    # 2) إشعار دوري كل notify_interval درجة
    c1 = reading.c1
    if kiln.notify_enabled and c1 is not None and kiln.notify_interval > 0:
        if c1 >= kiln.last_notified_temp + kiln.notify_interval:
            kiln.last_notified_temp = (int(c1) // kiln.notify_interval) * kiln.notify_interval
            send_notification(kiln, f"🌡️ الحرارة وصلت إلى {int(c1)}°C", db=db)
            log_event(db, kiln.id, "notification", f"🔔 الحرارة {int(c1)}°C",
                      message=f"وصلت الحرارة إلى {int(c1)}°C", color="#ffb74d", icon="🔔")
            changed = True

    # 3) تحذير تجاوز الدرجة النهائية
    x = reading.x
    if c1 is not None and x is not None and H not in (None, 0) and c1 > x + 5:
        send_notification(
            kiln,
            f"🚨 تحذير! الحرارة {int(c1)}°C تجاوزت الحد بـ {int(c1 - x)} درجة!",
            title="⚠️ خطر",
            db=db,
        )

    if changed:
        db.commit()


# ─────────────────────────────────────────────
#  تسجيل الأحداث المهمة (سجل الأحداث / الأرشيف)
# ─────────────────────────────────────────────

def log_event(db, kiln_id: str, event_type: str, title: str,
              message: str = "", color: str = "#9e9e9e", icon: str = "•") -> None:
    """يسجّل حدثاً في جدول events."""
    from app.models.kiln import Event
    try:
        ev = Event(
            kiln_id=kiln_id, type=event_type, title=title,
            message=message, color=color, icon=icon,
        )
        db.add(ev)
        db.commit()
    except Exception as e:
        print(f"❌ خطأ تسجيل الحدث: {e}")
        db.rollback()
