# DocIntel backend: one image for the API and the background workers.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_THREAD_LIMIT=1

# Tesseract OCR (English + orientation detection) and the small libraries OpenCV needs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN pip install -r requirements.txt \
 && if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi

COPY app ./app
COPY tests ./tests
COPY pytest.ini ./

# Run as a normal user, never as root.
RUN useradd --create-home --uid 10001 docintel && mkdir -p /data && chown docintel /data
USER docintel

EXPOSE 8000
# keep-alive longer than the proxy's idle timeout, so a reused connection is never closed mid-request (prevents random 502s)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--timeout-keep-alive", "120"]
