"""
═══════════════════════════════════════════════════════════════
  قاعدة البيانات (database.py)
═══════════════════════════════════════════════════════════════

يدعم SQLite (تطوير) و PostgreSQL (إنتاج) بنفس الكود.
التبديل يتم فقط عبر DATABASE_URL في متغيّرات البيئة.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

# بعض المنصات تعطي رابطاً يبدأ بـ postgres:// (صيغة قديمة)،
# بينما SQLAlchemy 2.0 يحتاج postgresql://
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

if _db_url.startswith("sqlite"):
    # SQLite: إعداد خاص للسماح بالاستخدام عبر خيوط متعددة
    engine = create_engine(_db_url, connect_args={"check_same_thread": False})
else:
    # PostgreSQL (إنتاج): تجمّع اتصالات يتحمّل مستخدمين كثيرين
    engine = create_engine(
        _db_url,
        pool_size=10,         # اتصالات دائمة
        max_overflow=20,      # اتصالات إضافية وقت الذروة
        pool_pre_ping=True,   # يتأكد أن الاتصال حيّ قبل الاستخدام
        pool_recycle=1800,    # يجدّد الاتصال كل 30 دقيقة
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """يُعطي جلسة قاعدة بيانات لكل طلب ثم يغلقها. (FastAPI dependency)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """ينشئ الجداول إن لم تكن موجودة."""
    import app.models.user   # noqa
    import app.models.kiln    # noqa
    Base.metadata.create_all(bind=engine)
