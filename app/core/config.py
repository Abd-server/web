"""
═══════════════════════════════════════════════════════════════
  الإعدادات (config.py) — القطعة 1-ب
═══════════════════════════════════════════════════════════════

تقرأ الإعدادات الحسّاسة من متغيّرات البيئة (.env) بدل كتابتها في الكود.
هذا يعالج الملاحظة المهمة من القطعة 1-أ حول JWT_SECRET.

كيف تستعمله:
  1) أنشئ ملف .env بجانب المشروع (لا ترفعه على GitHub أبداً).
  2) ضع فيه:
       JWT_SECRET=<السرّ المولّد>
       DATABASE_URL=sqlite:///./demo.db
  3) توليد سرّ قوي:
       python3 -c "import secrets; print(secrets.token_urlsafe(48))"
"""
from __future__ import annotations

import os


class Settings:
    # يقرأ من البيئة؛ وإن غاب، يستخدم القيمة المؤقتة (للتجربة المحلية فقط).
    JWT_SECRET: str = os.environ.get(
        "JWT_SECRET", "CHANGE_ME_USE_ENV_VARIABLE_IN_PRODUCTION"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 30
    REFRESH_TOKEN_DAYS: int = 14
    BCRYPT_ROUNDS: int = 12

    # قاعدة البيانات: SQLite الآن، ونغيّرها لـ PostgreSQL لاحقاً بتغيير هذا السطر فقط.
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./demo.db")

    @classmethod
    def is_production_ready(cls) -> bool:
        """تحذير إن كان السرّ ما زال القيمة المؤقتة."""
        return cls.JWT_SECRET != "CHANGE_ME_USE_ENV_VARIABLE_IN_PRODUCTION"


settings = Settings()
