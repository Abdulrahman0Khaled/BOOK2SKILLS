FROM python:3.11-slim

WORKDIR /app

# نظام dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-ara \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# المشروع
COPY . .

# مجلدات التشغيل
RUN mkdir -p /app/cache /app/outputs /app/data && chmod -R 777 /app/cache /app/outputs /app/data

# Ports
EXPOSE 8000

# Default: CLI
ENTRYPOINT ["book2skills"]
CMD ["--help"]
