# ═══════════════════════════════════════════════════════════
#  Dockerfile — منصة الأفران (FastAPI)
# ═══════════════════════════════════════════════════════════
FROM python:3.11-slim

# إعدادات بايثون للإنتاج
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# تثبيت المتطلبات أولاً (طبقة Docker مخبّأة لتسريع البناء)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# المنفذ الذي يستمع عليه التطبيق
EXPOSE 8000

# تشغيل الخادم (عدة workers لتحمّل مستخدمين كثيرين)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
