# Troubleshooting Guide

> دليل حل المشكلات الشائعة في نظام Book-to-Skills.

## 🔧 مشاكل شائعة وحلولها

### ❌ "ModuleNotFoundError: No module named 'book_to_skills'"

```bash
# الحل: تثبيت الحزمة في وضع التطوير
pip install -e .

# أو تأكد من أنك في البيئة الصحيحة
source .venv/bin/activate
pip install -e ".[dev]"
```

### ❌ خطأ OCR: "tesseract not found"

```bash
# Linux
sudo apt-get install tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng

# أو تعطيل OCR
# في .env
B2S_EXTRACTOR__USE_OCR_FALLBACK=false
```

### ❌ "API key not configured" أو "401 Unauthorized"

```bash
# تأكد من ضبط مفتاح API في .env
B2S_LLM__API_KEY=sk-your-actual-key

# تحقق من صحة المفتاح
# curl -H "Authorization: Bearer $B2S_LLM__API_KEY" https://api.openai.com/v1/models
```

### ❌ ChromaDB أخطاء

```bash
# مسح الـ vector store وإعادة بنائه
rm -rf data/vector_store/
book2skills clear cache
```

### ❌ "File hash mismatch" أو معالجة كل شيء من جديد

```bash
# مسح الـ cache
book2skills clear cache

# أو تعطيل incremental mode
# في .env
B2S_INCREMENTAL_MODE=false
```

### ❌ بطء في معالجة PDF

```bash
# تجربة 3 إعدادات مختلفة:
# 1. direct extraction (أسرع)
B2S_EXTRACTOR__PDF_EXTRACTION_MODE=direct

# 2. hybrid extraction (توازن)
B2S_EXTRACTOR__PDF_EXTRACTION_MODE=hybrid

# 3. OCR (أبطأ لكن أدق)
B2S_EXTRACTOR__PDF_EXTRACTION_MODE=ocr

# أيضاً قلل الـ DPI
B2S_EXTRACTOR__DPI=150
```

### ❌ Pipeline يتوقف عند مرحلة knowledge

```bash
# تحقق من الاتصال بـ LLM
B2S_LLM__TIMEOUT_S=300  # زيادة timeout

# أو استخدم موديل أصغر
B2S_LLM__MODEL_LARGE=gpt-4o-mini  # مؤقتاً للاختبار
```

### ❌ خطأ "Too many files open"

```bash
# Linux: زيادة حد الملفات المفتوحة
ulimit -n 4096

# أو استخدم memory cache بدل disk
B2S_CACHE__BACKEND=memory
```

### ❌ MyPy يشتكي من imports

تجاهل الأخطاء بسبب مكتبات خارجية. MyPy يتجاهل:
- pytest, pytest_asyncio
- pypdf, python-docx
- chromadb, sentence_transformers

هذا مضبوط في `pyproject.toml` تحت `[[tool.mypy.overrides]]`

### ❌ Ruff يشتكي من تنسيق

```bash
# تصحيح تلقائي
ruff check --fix src/ tests/
ruff format src/ tests/

# تحقق فقط
ruff check src/ tests/
ruff format src/ tests/ --check
```

## 🐳 Docker مشاكل

### "connection refused" مع ChromaDB

تأكد من أن ChromaDB يشتغل في نفس الشبكة:
```yaml
# docker-compose.yml
services:
  chromadb:
    networks:
      - app-network
```

### "permission denied" على cache/

```bash
# في Dockerfile
RUN mkdir -p /app/cache /app/outputs /app/data && chmod -R 777 /app/cache /app/outputs /app/data
```

## 📊 التحقق من صحة النظام

```bash
# 1. تحقق من Python version
python3 --version  # يجب ≥ 3.11

# 2. تحقق من المكتبات المثبتة
pip list | grep -E "fastapi|pydantic|typer|pypdf|docx"

# 3. تحقق من OCR
tesseract --list-langs  # تحقق من وجود ara+eng

# 4. تشغيل اختبارات سريعة
pytest -m "not integration and not e2e" -q

# 5. تحقق من API
curl http://localhost:8000/api/v1/health
```

## 🤔 لا يزال لديك مشكلة؟

1. تحقق من logs: `cat logs/pipeline.log`
2. شغّل في وضع debug: `B2S_MONITORING__LOG_LEVEL=DEBUG`
3. شغّل اختبارات مع verbose: `pytest -v --tb=long`
4. تأكد من `.env` إعدادات
5. افتح Issue في المستودع
