# Рефакторинг VPN Aggregator — Фаза 2 (Оптимизация производительности)

## ✅ Выполнено

### 1. Async HTTP Fetcher
**Файл:** `scripts/async_fetcher.py`

Заменён синхронный `requests` на `aiohttp`:
- **Параллельная загрузка** до 20 источников одновременно (configurable)
- **Rate limiting** через `asyncio.Semaphore`
- **Retry с exponential backoff** (3 попытки, задержка 1s → 2s → 4s)
- **Graceful error handling** — один упавший источник не ломает весь процесс
- **Метрики** — duration_ms для каждого запроса

**Производительность:**
- Было: 237 источников × 10s timeout = до 40 минут последовательно
- Стало: 237 источников / 20 параллельных = ~2 минуты (при успешных запросах)

### 2. Async DNS Resolver
**Файл:** `scripts/async_dns.py`

Асинхронный DNS lookup с кэшированием:
- **aiodns** для неблокирующего DNS (fallback на `socket.gethostbyname`)
- **Кэширование** результатов с TTL 1 час
- **Batch processing** — резолвит до 50 хостов параллельно
- **Статистика кэша** — отслеживание hit rate

**Производительность:**
- Было: 3000 нод × 2s timeout = до 100 минут последовательно
- Стало: 3000 нод / 50 параллельных = ~2 минуты + кэш

### 3. Async Enricher
**Файл:** `scripts/async_enricher.py`

Улучшенная версия `enricher.py`:
- **Batch processing** по 100 нод за раз
- **Async DNS** через `AsyncDNSResolver`
- **Переиспользование GeoIP readers** (не создаём каждый раз)
- **Кэширование DNS** между батчами

### 4. Интеграция в pipeline.py
**Обновлён:** `pipeline.py`

- Функция `ingest_sources()` теперь использует `async_fetcher`
- Импорт `fetch_sources_sync`, `FetcherConfig`
- Все источники загружаются параллельно одним вызовом

### 5. Обновлены зависимости
**Файл:** `requirements.txt`

Добавлены:
- `aiodns>=3.1.0` — async DNS
- `aiofiles>=23.2.0` — async file I/O (для будущего)

---

## 📊 Метрики производительности

### До оптимизации (Фаза 1)
```
Загрузка источников: ~40 минут (последовательно)
DNS resolve:         ~100 минут (последовательно, 3000 нод)
GeoIP lookup:        ~30 секунд (быстро, но после DNS)
───────────────────────────────────────────────────
Итого:               ~140 минут
```

### После оптимизации (Фаза 2)
```
Загрузка источников: ~2 минуты (20 параллельных)
DNS resolve:         ~2 минуты (50 параллельных + кэш)
GeoIP lookup:        ~30 секунд (без изменений)
───────────────────────────────────────────────────
Итого:               ~5 минут (ускорение в 28×)
```

---

## 🎯 Использование

### Старый код (обратная совместимость)
```python
# pipeline.py работает как раньше
python pipeline.py
```

### Новый async enricher
```python
from scripts.async_enricher import AsyncEnricher

enricher = AsyncEnricher(
    enable_dns=True,
    enable_geoip=True,
    batch_size=100,
)
enricher.enrich_all(nodes)

# Статистика DNS кэша
stats = enricher.get_dns_cache_stats()
print(f"DNS cache: {stats['valid']}/{stats['total']} valid")
```

### Async fetcher напрямую
```python
from scripts.async_fetcher import fetch_sources_sync, FetcherConfig

config = FetcherConfig(
    max_concurrent=20,
    timeout=10,
    max_retries=3,
)

sources = [
    {"name": "source1", "url": "https://..."},
    {"name": "source2", "url": "https://..."},
]

results = fetch_sources_sync(sources, config)
for r in results:
    if r.success:
        print(f"✓ {r.name}: {len(r.content)} bytes in {r.duration_ms}ms")
    else:
        print(f"✗ {r.name}: {r.error}")
```

---

## 🔧 Следующие шаги (Фаза 3)

### Улучшение качества данных
1. **Provider hunter** — парсинг remark для определения первоисточников
2. **Alive checker** — async TCP ping как отдельный модуль
3. **Умный repacker** — применение format_template из config.yaml

### Персистентность
4. **SQLite для истории** — трекинг метрик источников во времени
5. **Инкрементальные обновления** — кэширование хешей источников
6. **Автоматический whitelist/blacklist** — на основе score + тегов

---

## ✅ Проверка

```bash
# Компиляция
python -m py_compile pipeline.py scripts/async_*.py

# Запуск
python pipeline.py
# или
python cli.py full
```

---

## 📝 Совместимость

- ✅ Обратная совместимость с Фазой 1
- ✅ Старый `enricher.py` не тронут (можно использовать оба)
- ✅ `pipeline.py` работает с новым async fetcher
- ✅ Fallback на синхронный DNS если `aiodns` недоступен
