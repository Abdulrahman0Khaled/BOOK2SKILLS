# ADR-004: Cache and Queue Strategy

**التاريخ:** 2026-07-30  
**الحالة:** ✅ Approved  

## Context

الـ Pipeline يحتاج:
1. **Cache**: تجنب إعادة معالجة نفس الملف
2. **Queue**: إدارة المهام المتزامنة

## Decision

### Cache: Hash-based Incremental + Dual Backend

```python
# Disk for persistence, Memory for speed
cache.get(f"{stage}:{file_hash}")  # ← hash-based key
```

- **Disk backend** (default): JSON files, TTL 7 أيام
- **Memory backend** (optional): dict, سريع لكن مؤقت
- Hash = SHA-256 للملف

### Queue: Priority-based + Dual Backend

```python
queue.enqueue(task, priority=QUEUE.HIGH)
```

- **Memory backend** (default): asyncio.Queue
- **Redis backend** (optional): RQ للـ production
- Priorities: CRITICAL > HIGH > MEDIUM > LOW > BATCH

## Consequences

### Positive
- Cache يمنع إعادة المعالجة غير الضرورية
- Hash-based detection دقيق وسريع
- Queue يتحكم في التزامن
- التبديل بين backends سهل

### Trade-offs
- Disk cache يستهلك مساحة
- Memory cache يفقد البيانات عند إعادة التشغيل
- Redis يحتاج تشغيل خدمة منفصلة
