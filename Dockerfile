# Multi-stage build: küçük final image
FROM python:3.11-slim as builder

WORKDIR /app

# Requirements install et
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final stage: sadece runtime gerekli
FROM python:3.11-slim

WORKDIR /app

# Builder'dan installed packages'ları kopyala
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Kod dosyalarını kopyala
COPY app/ ./app/

# Port açık
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# App başlat
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]