"""
═══════════════════════════════════════════════════════════════
  بوت تيليجرام المركزي (telegram_bot.py) — المرحلة ب
═══════════════════════════════════════════════════════════════

بوت واحد لكل المنصة. كل عميل يربط حسابه مرة واحدة عبر رمز مؤقت،
فتصله إشعارات جميع أفرانه على نفس المحادثة.

آلية الربط:
  1) العميل يضغط "ربط تيليجرام" في الموقع → ننشئ رمزاً مؤقتاً TG-xxxxxx
  2) يفتح البوت ويرسل الرمز
  3) تيليجرام يستدعي webhook عندنا → نطابق الرمز → نحفظ chat_id

ملاحظة: نستخدم urllib القياسية (بدون مكتبات إضافية).
"""
from __future__ import annotations

import json
import random
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

from app.core.config import settings


LINK_CODE_MINUTES = 10  # صلاحية رمز الربط


def _api(method: str, payload: dict) -> dict:
    """ينفّذ نداءً لواجهة بوت تيليجرام."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return {}
    try:
        data = urllib.parse.urlencode(payload).encode()
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"❌ خطأ تيليجرام API ({method}): {e}")
        return {}


def send_message(chat_id: str, text: str) -> None:
    _api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def generate_link_code(user, db) -> str:
    """ينشئ رمز ربط مؤقت للعميل ويحفظه على حسابه."""
    code = "TG-" + "".join(random.choices("0123456789", k=6))
    user.telegram_link_code = code
    user.telegram_link_expires = datetime.now(timezone.utc) + timedelta(minutes=LINK_CODE_MINUTES)
    db.commit()
    return code


def _match_link_code(code: str, db):
    """يبحث عن مستخدم يملك رمز الربط هذا وغير منتهٍ. يرجّع المستخدم أو None."""
    from app.models.user import User
    code = code.strip().upper()
    user = db.query(User).filter(User.telegram_link_code == code).first()
    if user is None:
        return None
    exp = user.telegram_link_expires
    if exp is not None:
        # توحيد المنطقة الزمنية للمقارنة
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            return None
    return user


def handle_update(update: dict, db) -> None:
    """
    يعالج تحديثاً واردًا من webhook تيليجرام.
    يدعم: /start  ورسائل رمز الربط TG-xxxxxx.
    """
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()
    if not chat_id:
        return

    # أمر البداية
    if text.startswith("/start"):
        send_message(
            chat_id,
            "👋 أهلاً بك في <b>منصة فران فاخر</b>!\n\n"
            "لربط حسابك، افتح الموقع واضغط على <b>«ربط تيليجرام»</b>، "
            "ثم أرسل لي الرمز الذي يظهر لك (يبدأ بـ <code>TG-</code>).",
        )
        return

    # محاولة ربط عبر الرمز
    if text.upper().startswith("TG-"):
        user = _match_link_code(text, db)
        if user is None:
            send_message(
                chat_id,
                "❌ الرمز غير صحيح أو انتهت صلاحيته.\n"
                "ارجع للموقع واضغط «ربط تيليجرام» للحصول على رمز جديد.",
            )
            return
        # ربط ناجح
        user.telegram_chat = chat_id
        user.telegram_link_code = None
        user.telegram_link_expires = None
        db.commit()
        send_message(
            chat_id,
            "✅ <b>تم الربط بنجاح!</b>\n\n"
            "ستصلك الآن إشعارات أفرانك هنا: تغيّر المرحلة، "
            "الوصول لدرجات الحرارة، والتحذيرات. 🔥🌡️",
        )
        return

    # رسالة غير معروفة
    send_message(
        chat_id,
        "لم أفهم رسالتك 🤔\n"
        "أرسل رمز الربط الذي يظهر في الموقع (يبدأ بـ <code>TG-</code>).",
    )
