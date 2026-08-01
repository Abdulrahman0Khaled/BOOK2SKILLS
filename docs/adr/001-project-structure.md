# ADR-001: Project Structure and Clean Architecture

**التاريخ:** 2026-07-30  
**الحالة:** ✅ Approved  

## Context

بناء نظام Pipeline يحول الكتب إلى AI Agent Skills (متوافقة مع OpenClaw, Claude, Codex, Hermes...). نحتاج هيكل مشروع يدعم:
- 10 مراحل مستقلة قابلة للتوسع
- LLM Providers متعددة
- سهولة الاختبار والصيانة
- قابلية النشر (Docker, CI/CD)

## Options

### Option 1: Monolithic Structure
كل الكود في ملفات قليلة. بسيط لكن يصعب صيانته.

### Option 2: Feature-based Structure
تجميع الكود حسب الميزة (pipeline/, llm/...) — اخترنا هذا.

### Option 3: Hexagonal Architecture
طبقات Ports/Adapters. قوي لكن معقد لهذا الحجم.

## Decision

**اخترنا Clean Architecture مع هيكل Feature-based:**

```
src/book_to_skills/
├── pipeline/      # 10 Pipeline Stages
├── llm/           # LLM Providers
├── extractors/    # Document Extractors
├── storage/       # File Storage
├── cache/         # Cache
├── queue/         # Task Queue
├── monitoring/    # Logging & Metrics
├── domain/        # Models & Enums
├── orchestration/ # n8n Integration
├── config.py      # Configuration
├── main.py        # CLI
└── api.py         # FastAPI
```

### الأسس
1. **Dependency Injection**: كل component يستقبل config في constructor
2. **Interfaces**: Base classes لكل layer
3. **Single Responsibility**: كل module مسؤول عن شيء واحد
4. **Independent Stages**: كل stage يمكن تشغيله منفرداً

## Consequences

### Positive
- سهولة إضافة Stages/Providers جديدة
- اختبار كل layer بشكل مستقل
- إمكانية تشغيل stages بشكل متوازٍ
- DI يسهل الـ mocking في الاختبارات

### Trade-offs
- عدد files أكبر من monolithic
- يحتاج فهم Clean Architecture
- Overhead لـ DI في المشاريع الصغيرة لكن مناسب هنا
