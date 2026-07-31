# ADR-002: LLM Abstraction Layer

**التاريخ:** 2026-07-30  
**الحالة:** ✅ Approved  

## Context

النظام يحتاج دعم مزودي LLM متعددين (OpenAI, Anthropic, Gemini, Ollama, OpenRouter).
كل مزود له SDK مختلف، تنسيق requests مختلف، وأسعار مختلفة.

## Options

### Option 1: Direct SDK Usage
استخدام SDK كل مزود مباشرة. سريع للبدء لكن صعب التبديل بين المزودين.

### Option 2: Unified Interface (اخترنا هذا)
طبقة تجريدية توحد كل المزودين تحت interface واحد.

### Option 3: LangChain/LiteLLM Integration
استخدام مكتبة طرف ثالث. قوي لكن dependency كبيرة وقيود.

## Decision

**اخترنا Unified Interface مع Factory Pattern:**

```python
class BaseLLMProvider(ABC):
    async def generate(...) -> LLMResponse
    async def generate_structured(...) -> BaseModel
    async def generate_with_retry(...) -> LLMResponse

class OpenAIProvider(BaseLLMProvider): ...
class AnthropicProvider(BaseLLMProvider): ...
```

### Small vs Large Model Strategy
- **Small Model** (gpt-4o-mini): للمهام البسيطة (تنظيف، تقطيع، تصنيف) ← أرخص وأسرع
- **Large Model** (gpt-4o): للمهام المعقدة (استخراج معرفة، توليد، مراجعة) ← أدق

## Consequences

### Positive
- تبديل المزود بسطر config
- اختبار mock providers بسهولة
- Small/Large model استراتيجية تحسن التكلفة
- إضافة مزود جديد = class جديد فقط

### Trade-offs
- بعض ميزات SDK الفريدة可能要 تضيع في التجريد
- Performance overhead طفيف
- يحتاج صيانة لمواكبة تغييرات SDK
