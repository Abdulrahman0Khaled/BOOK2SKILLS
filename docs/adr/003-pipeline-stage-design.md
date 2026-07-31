# ADR-003: Pipeline Stage Design

**التاريخ:** 2026-07-30  
**الحالة:** ✅ Approved  

## Context

الـ Pipeline يحوي 10 مراحل. كل مرحلة:
- تستقبل `PipelineContext`
- تعالجه
- ترجعه مع إضافات

## Decision

**اخترنا Context Object Pattern + BaseStage abstract class:**

```python
class BaseStage(ABC):
    async def process(self, context: PipelineContext) -> PipelineContext
    async def execute(self, context) -> ProcessingResult
    def get_cache_key(self, context) -> str | None
```

### PipelineContext
- `run_id`: معرف الجلسة
- `book`: معلومات الكتاب
- `extracted` ← `cleaned` ← `chunks` ← `knowledge_units` ← `skills`
- `errors[]`: أخطاء كل مرحلة
- `stage_results{}`: نتائج كل مرحلة

### Independence
كل مرحلة:
- تعمل بشكل مستقل
- لها Cache Key خاص
- لها Metrics خاصة
- يمكن تشغيلها منفردة

## Consequences

### Positive
- Stages قابلة للاختبار المنفرد
- إضافة/إزالة stage بدون تأثير على الآخرين
- Cache لكل stage يحسن الأداء
- Context Object يوفر traceability كاملة

### Trade-offs
- Context object يكبر كلما تقدم الـ Pipeline
- بعض البيانات قد تكون في الـ Context لكن ليست مطلوبة
