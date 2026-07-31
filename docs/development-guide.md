# Development Guide

> دليل التطوير للمساهمين في مشروع Book-to-Skills.

## 🛠️ الإعداد

```bash
# Clone
git clone https://github.com/Abdulrahman0Khaled/BOOK2SKILLS.git
cd BOOK2SKILLS

# Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# إعداد pre-commit (اختياري)
pip install pre-commit
pre-commit install
```

## 🧪 إجراءات التطوير

### 1. TDD First

كل feature جديد يبدأ باختبار فاشل:

```bash
# 1. اكتب الاختبار
# 2. تأكد من فشله
pytest tests/unit/test_new_feature.py -v

# 3. نفذ الكود
# 4. تأكد من نجاحه
pytest tests/unit/test_new_feature.py -v

# 5. راجع وتأكد من عدم كسر شيء
pytest -q
```

### 2. Quality Gates

```bash
# Ruff (lint + format)
ruff check src/ tests/
ruff format src/ tests/ --check

# MyPy type checking
mypy src/

# Full test suite
pytest --cov=book_to_skills -v
```

### 3. Git Workflow

```
main ←── develop ←── feature/xxx
                      ├── fix/xxx
                      └── refactor/xxx
```

- **feature/**: ميزات جديدة
- **fix/**: إصلاح أخطاء
- **refactor/**: تحسين كود

Commit messages:
```
feat(pipeline): add new XYZ stage
fix(extractor): handle empty PDF pages
refactor(cache): simplify disk backend
docs(api): add endpoint examples
test(domain): add KnowledgeUnit tests
```

### 4. Adding a New Pipeline Stage

1. إنشاء ملف في `src/book_to_skills/pipeline/`
2. وراثة `BaseStage`
3. تطبيق `async def process(self, context) -> PipelineContext`
4. إضافة اختبارات
5. إضافة stage إلى `stages_enabled` في config
6. إضافة إلى `PipelineOrchestrator`

```python
from .base import BaseStage
from ..domain.models import PipelineContext

class MyNewStage(BaseStage):
    async def process(self, context: PipelineContext) -> PipelineContext:
        # Your logic here
        return context
```

### 5. Adding a New LLM Provider

1. إنشاء ملف في `src/book_to_skills/llm/`
2. وراثة `BaseLLMProvider`
3. تطبيق `generate()` و `generate_structured()`
4. إضافة إلى `provider_factory.py`
5. إضافة إلى `LLMProvider` enum

### 6. Testing

```bash
# Unit tests (سريعة، بدون dependencies خارجية)
pytest -m unit -v

# Integration tests (تحتاج مكتبات مثبتة)
pytest -m integration -v

# E2E tests (كاملة)
pytest -m e2e -v

# Slow tests
pytest -m slow -v

# All except slow
pytest -m "not slow" -v
```

## 📝 Coding Standards

### Python
- Python 3.11+ type hints
- 100 char line length
- Ruff linting (config في pyproject.toml)
- Google-style docstrings
- SOLID principles
- Composition over inheritance

### Naming
- Classes: PascalCase
- Functions/Methods: snake_case
- Constants: UPPER_CASE
- Private: _prefix

### Imports Order
1. Python standard library
2. Third-party
3. Local

## 🐳 Docker Development

```bash
# Build
docker build -f docker/Dockerfile -t book-to-skills .

# Run with compose
docker-compose -f docker/docker-compose.yml up -d

# Run tests in container
docker run --rm book-to-skills pytest -v
```

## 📊 Monitoring

```bash
# Check logs
tail -f logs/pipeline.log

# Check cache size
du -sh cache/

# Check output skills
ls -la outputs/skills/

# Check vector DB
ls -la data/vector_store/
```

## 🚀 Release Process

1. تحديث الإصدار في `pyproject.toml`
2. تشغيل كامل الاختبارات
3. تحديث التوثيق
4. إنشاء Git Tag
5. Push إلى GitHub
6. CI/CD ينشر تلقائياً
