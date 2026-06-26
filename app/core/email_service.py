"""
═══════════════════════════════════════════════════════════════
  خدمة الإيميل (email_service.py)
═══════════════════════════════════════════════════════════════

ترسل إيميلات عبر SMTP (Gmail). تُستخدم لاسترجاع كلمة المرور.
الإعدادات تأتي من متغيّرات البيئة (SMTP_USER, SMTP_PASSWORD).

إعداد Gmail (مرة واحدة):
  1) أنشئ حساب Gmail للمنصة (مثلاً furanfakhar.system@gmail.com).
  2) فعّل المصادقة الثنائية (2-Step Verification).
  3) أنشئ "كلمة مرور تطبيق" (App Password) من إعدادات أمان جوجل.
  4) ضع في متغيّرات البيئة:
       SMTP_USER=furanfakhar.system@gmail.com
       SMTP_PASSWORD=<كلمة مرور التطبيق المكوّنة من 16 حرفاً>
"""
from __future__ import annotations

import json
import smtplib
import ssl
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from app.core.config import settings


def _send_via_resend(to_email: str, subject: str, html_body: str) -> bool:
    """يرسل عبر Resend HTTP API. يرجّع True لو نجح."""
    try:
        payload = json.dumps({
            "from": f"{settings.SMTP_FROM_NAME} <{settings.EMAIL_FROM}>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            if ok:
                print("✅ تم إرسال الإيميل عبر Resend")
            return ok
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        print(f"❌ فشل إرسال الإيميل عبر Resend: {e.code} {body}")
        return False
    except Exception as e:
        print(f"❌ فشل إرسال الإيميل عبر Resend: {e}")
        return False


def _send_via_smtp(to_email: str, subject: str, html_body: str) -> bool:
    """بديل: يرسل عبر Gmail SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_USER))
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        context = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, to_email, msg.as_string())
        print("✅ تم إرسال الإيميل عبر SMTP")
        return True
    except Exception as e:
        print(f"❌ فشل إرسال الإيميل عبر SMTP: {e}")
        return False


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """يرسل إيميل HTML. يفضّل Resend، وإلا Gmail SMTP."""
    if settings.resend_configured():
        return _send_via_resend(to_email, subject, html_body)
    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        return _send_via_smtp(to_email, subject, html_body)
    print("⚠️ الإيميل غير مُعدّ (لا Resend ولا SMTP)")
    return False


def send_reset_code(to_email: str, code: str, full_name: str = "") -> bool:
    """يرسل رمز استرجاع كلمة المرور."""
    greeting = f"مرحباً {full_name}،" if full_name else "مرحباً،"
    html = f"""
    <div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;max-width:480px;
         margin:0 auto;padding:24px;background:#0f1117;color:#e8e8e8;border-radius:16px;">
      <h2 style="color:#f953c6;margin-top:0;">🔥 منصة الأفران</h2>
      <p>{greeting}</p>
      <p>طلبت إعادة تعيين كلمة المرور. استخدم الرمز التالي (صالح لمدة 15 دقيقة):</p>
      <div style="font-size:34px;font-weight:bold;letter-spacing:10px;color:#4aa8ff;
           text-align:center;background:#1a1d27;padding:18px;border-radius:12px;margin:18px 0;">
        {code}
      </div>
      <p style="color:#888;font-size:13px;">
        إذا لم تطلب هذا، تجاهل الرسالة وكلمة مرورك تبقى آمنة.
      </p>
    </div>
    """
    return send_email(to_email, "رمز إعادة تعيين كلمة المرور - منصة الأفران", html)
