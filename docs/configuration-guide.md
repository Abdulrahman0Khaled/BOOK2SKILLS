# Configuration Guide

> دليل الإعدادات الكامل لنظام Book-to-Skills Pipeline.

## 📋 طرق الإعداد

1. **معالج الإعداد التفاعلي (Studio TUI Wizard)** — الإسهل والأسرع مباشرة من التيرمينال عبر `book2skills studio` برقم خيار `⚙️ Configure LLM Provider`.
2. **ملف .env** — حفظ التكوينات يدوياً في جذر المشروع.
3. **متغيرات البيئة (Environment Variables)** — للمسارات CI/CD و Docker.
4. **مباشر في الكود** — للاختبارات البرمجية.

### أولوية التطبيق:
مُتغير البيئة > ملف .env > الإعدادات الافتراضية

## ⚙️ جميع الإعدادات

### General

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_DEBUG` | `false` | وضع التصحيح |
| `B2S_DATA_DIR` | `data` | مجلد البيانات |
| `B2S_MAX_WORKERS` | `4` | عدد العمال المتوازيين |
| `B2S_INCREMENTAL_MODE` | `true` | معالجة الملفات الجديدة فقط |
| `B2S_SKIP_ON_ERROR` | `false` | تخطي المرحلة عند الخطأ |
| `B2S_RUN_PARALLEL_STAGES` | `false` | تشغيل المراحل المتوازية |

### LLM

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_LLM__PROVIDER` | `openai` | مزود الخدمة |
| `B2S_LLM__API_KEY` | `""` | مفتاح API |
| `B2S_LLM__BASE_URL` | `""` | رابط مخصص |
| `B2S_LLM__MODEL_SMALL` | `gpt-4o-mini` | موديل للمهام البسيطة |
| `B2S_LLM__MODEL_LARGE` | `gpt-4o` | موديل للمهام المعقدة |
| `B2S_LLM__TEMPERATURE` | `0.3` | درجة الإبداع |
| `B2S_LLM__MAX_TOKENS` | `4096` | الحد الأقصى للتوكنز |
| `B2S_LLM__TIMEOUT_S` | `120` | مهلة الطلب بالثواني |
| `B2S_LLM__MAX_RETRIES` | `3` | عدد إعادة المحاولة |

### Extractor

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_EXTRACTOR__USE_OCR_FALLBACK` | `true` | استخدام OCR كبديل |
| `B2S_EXTRACTOR__OCR_LANGUAGES` | `ara+eng` | لغات OCR |
| `B2S_EXTRACTOR__PDF_EXTRACTION_MODE` | `hybrid` | طريقة الاستخراج |
| `B2S_EXTRACTOR__MAX_PAGES` | `500` | الحد الأقصى للصفحات |
| `B2S_EXTRACTOR__DPI` | `300` | دقة OCR |

### Chunk

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_CHUNK__STRATEGY` | `semantic` | استراتيجية التقطيع |
| `B2S_CHUNK__MAX_CHUNK_WORDS` | `1500` | الحد الأقصى لكلمات القطعة |
| `B2S_CHUNK__MIN_CHUNK_WORDS` | `100` | الحد الأدنى لكلمات القطعة |
| `B2S_CHUNK__OVERLAP_WORDS` | `150` | تداخل الكلمات بين القطع |
| `B2S_CHUNK__SPLIT_AT_HEADINGS` | `true` | التقسيم عند العناوين |

### Knowledge

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_KNOWLEDGE__MIN_CONFIDENCE` | `0.3` | الحد الأدنى للثقة |
| `B2S_KNOWLEDGE__MAX_UNITS_PER_CHUNK` | `10` | الحد الأقصى للوحدات لكل قطعة |

### Cache

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_CACHE__ENABLED` | `true` | تفعيل التخزين المؤقت |
| `B2S_CACHE__BACKEND` | `disk` | نوع التخزين المؤقت |
| `B2S_CACHE__CACHE_DIR` | `cache` | مجلد التخزين المؤقت |
| `B2S_CACHE__TTL_HOURS` | `168` | مدة الصلاحية (7 أيام) |
| `B2S_CACHE__MAX_SIZE_MB` | `1024` | الحجم الأقصى |

### Queue

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_QUEUE__BACKEND` | `memory` | نوع الطابور |
| `B2S_QUEUE__REDIS_URL` | `redis://localhost:6379/0` | رابط Redis |
| `B2S_QUEUE__MAX_CONCURRENT_JOBS` | `4` | الحد الأقصى للوظائف المتزامنة |

### Vector DB

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_VECTOR_DB__BACKEND` | `chroma` | نوع قاعدة المتجهات |
| `B2S_VECTOR_DB__PERSIST_DIR` | `data/vector_store` | مجلد التخزين |
| `B2S_VECTOR_DB__COLLECTION_NAME` | `book_skills` | اسم المجموعة |
| `B2S_VECTOR_DB__EMBEDDING_DIM` | `384` | أبعاد المتجه |
| `B2S_VECTOR_DB__DISTANCE_METRIC` | `cosine` | مقياس المسافة |

### Storage

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_STORAGE__SKILLS_DIR` | `outputs/skills` | مجلد المهارات |
| `B2S_STORAGE__FORMAT` | `markdown` | صيغة التخزين |

### Monitoring

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `B2S_MONITORING__LOG_LEVEL` | `INFO` | مستوى التسجيل |
| `B2S_MONITORING__LOG_FORMAT` | `console` | صيغة التسجيل |
| `B2S_MONITORING__ENABLE_METRICS` | `true` | تفعيل المقاييس |
| `B2S_MONITORING__ENABLE_PROGRESS_BARS` | `true` | تفعيل أشرطة التقدم |

## 📝 مثال .env متكامل

```env
# == LLM ==
B2S_LLM__PROVIDER=openai
B2S_LLM__API_KEY=sk-proj-your-key-here
B2S_LLM__MODEL_SMALL=gpt-4o-mini
B2S_LLM__MODEL_LARGE=gpt-4o
B2S_LLM__TEMPERATURE=0.2

# == Extract ==
B2S_EXTRACTOR__USE_OCR_FALLBACK=true
B2S_EXTRACTOR__OCR_LANGUAGES=ara+eng
B2S_EXTRACTOR__PDF_EXTRACTION_MODE=hybrid

# == Cache ==
B2S_CACHE__ENABLED=true
B2S_CACHE__BACKEND=disk
B2S_CACHE__TTL_HOURS=168

# == Performance ==
B2S_MAX_WORKERS=8
B2S_INCREMENTAL_MODE=true

# == Vector ==
B2S_VECTOR_DB__BACKEND=chroma
B2S_VECTOR_DB__COLLECTION_NAME=book_skills
```
