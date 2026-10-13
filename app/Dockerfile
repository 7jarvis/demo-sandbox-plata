FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && useradd --system --uid 10001 --home-dir /srv cardpay \
 && mkdir -p /data && chown cardpay /data

COPY cardpay ./cardpay
USER cardpay

ENV DATABASE_PATH=/data/cardpay.db
EXPOSE 8000
HEALTHCHECK --interval=2s --timeout=3s --retries=30 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health').status != 200)"]
CMD ["uvicorn", "cardpay.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
