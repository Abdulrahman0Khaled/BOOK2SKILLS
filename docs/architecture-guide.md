# Architecture Guide

> دليل العمارة لنظام Book-to-Skills Pipeline.

## 🎯 النظرة العامة

النظام مبني على **Clean Architecture** مع 4 طبقات:

```
┌─────────────────────────────────────────┐
│           Presentation Layer            │
│         (CLI / FastAPI / n8n)           │
├─────────────────────────────────────────┤
│           Application Layer             │
│      (Pipeline Orchestrator)            │
├─────────────────────────────────────────┤
│            Domain Layer                 │
│   (Models, Enums, Business Logic)       │
├─────────────────────────────────────────┤
│           Infrastructure Layer          │
│ (LLM Providers, Extractors, Storage)    │
└─────────────────────────────────────────┘
```

## 🏛️ Clean Architecture Principles

### Dependency Injection
جميع المكونات تستقبل `PipelineConfig` في الـ constructor. لا يوجد hard dependencies.

### Interface Segregation
كل Base class (BaseStage, BaseLLMProvider, BaseExtractor) يحدد interface واضح.

### Single Responsibility
كل Pipeline Stage مسؤول عن مرحلة واحدة فقط من التحويل.

## 🔄 Pipeline Design

### Independent Stages
كل Stage:
- يعالج `PipelineContext` input ← ينتج `PipelineContext` output
- يمكن تشغيله منفرداً
- له Cache Key مستقل
- له Metrics خاصة به

### Context Object
`PipelineContext` هو **Single Source of Truth** للمراحل:
- يحوي كل حالة الـ Pipeline
- يمرر بين المراحل كـ immutable جزئياً
- يسجل الأخطاء والوقت

### Incremental Processing
- كل ملف book له Hash (SHA-256)
- إذا لم يتغير الـ hash، المراحل تتخطى المعالجة
- الـ cache يخزن نتائج كل مرحلة بمفتاح `{stage}:{file_hash}`

## 🧩 Plugin Architecture

```
Pipeline Stage Registration:
    Orchestrator ──→ List[BaseStage]
                         │
                    Factory Method
                    (يمكن إضافة Stages جديدة)
```

BaseStage يسمح بإضافة Stages جديدة بدون تعديل الموجود.

## 📊 Data Flow

```
1. Extract → ExtractedContent.text
2. Clean → CleanedContent.text
3. Chunk → list[TextChunk]
4. Knowledge → list[KnowledgeUnit]
5. SkillGen → list[HermesSkill]
6. Review → تحديث status + quality_score
7. Dedup → إزالة المكررات
8. KG → knowledge_graph.json
9. Embeddings → إضافة chunk.embedding
10. VectorDB → تخزين في ChromaDB
```

## 🔐 LLM Strategy

| Provider | Use Case |
|----------|----------|
| OpenAI (GPT-4o) | المعرفة والتوليد |
| Anthropic (Claude) | البديل الرئيسي |
| Gemini | بديل مجاني |
| Ollama | تشغيل محلي بدون إنترنت |
| OpenRouter | الوصول لـ 200+ موديل |

### Small vs Large Model
- **Small model** (gpt-4o-mini) ← تنظيف، تقطيع، تصنيف
- **Large model** (gpt-4o) ← استخراج معرفة، توليد مهارات، مراجعة

## 🗄️ Storage Strategy

| النوع | الموقع | الصيغة |
|-------|--------|--------|
| Cache | `cache/` | JSON |
| Skills | `outputs/skills/` | JSON + Markdown |
| Knowledge Graph | `outputs/knowledge_graph/` | JSON |
| Embeddings | `outputs/embeddings/` | NPZ |
| Vector DB | `data/vector_store/` | ChromaDB |

## 🚦 Queue System

يدعم:
- **Memory Queue** — افتراضي، للجلسات المحلية
- **Redis Queue** — اختياري، للإنتاج

```
enqueue(task) → Queue → dequeue() → Worker
                           │
                     Priority Queue
                     (CRITICAL > HIGH > MEDIUM > LOW)
```

## 📈 Performance Considerations

1. **Parallel Processing**: المراحل المستقلة يمكن تشغيلها بالتوازي
2. **Caching**: تجنب إعادة معالجة النتائج المؤقتة
3. **Incremental**: معالجة الملفات الجديدة فقط
4. **Hash-based**: اكتشاف التغييرات بدون مقارنة محتوى كامل
5. **Queue**: التحكم في التزامن مع قائمة انتظار

## 🔒 Scalability

- **Horizontal**: تشغيل Workers متعددة مع Redis Queue
- **Vertical**: زيادة max_workers للمعالجة المتوازية
- **Storage**: ChromaDB يقيس أفقياً
- **API**: FastAPI مع Uvicorn workers
