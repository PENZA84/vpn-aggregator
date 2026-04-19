# Рефакторинг VPN Aggregator — Фаза 1 (Декомпозиция)

## ✅ Выполнено

### 1. Создана структура констант
**Файл:** `scripts/constants.py`

Вынесены все магические числа и дублирующиеся константы:
- `EU_COUNTRIES`, `BAD_COUNTRIES` — географические константы
- Таймауты: `DEFAULT_DNS_TIMEOUT`, `DEFAULT_PING_TIMEOUT`, `DEFAULT_HTTP_TIMEOUT`
- Пороги для scoring и классификации источников
- Пороги для тегов whitelist/blacklist
- Константы для reporter и build_eu_subscriptions

**Обновлены модули:**
- `scripts/filters.py` — использует `EU_COUNTRIES`
- `scripts/profiler.py` — использует все scoring-константы
- `scripts/enricher.py` — использует таймауты и пути
- `scripts/reporter.py` — использует `REPORTER_MIN_NODES`, `REPORTER_MIN_UNIQUE_IPS`
- `build_eu_subscriptions_list.py` — использует `EU_COUNTRIES`, `KEYS_PER_SUBSCRIPTION`

### 2. Создан config loader с валидацией
**Файл:** `scripts/config_loader.py`

- Pydantic-модели для всех секций config.yaml
- Автоматический мерж с дефолтами
- Валидация структуры при загрузке
- Graceful fallback на дефолты при ошибках

**Модели:**
- `AppConfig`, `GeoFilterConfig`, `PerformanceFilterConfig`
- `FiltersConfig`, `QualityMetricsConfig`, `OutputConfig`
- `EncodingConfig`, `SourceEntry`, `SourcesConfig`, `EnricherConfig`
- Главная модель `Config`

### 3. Создан CLI с командами
**Файл:** `cli.py`

Разбит монолитный pipeline.py на отдельные команды:
```bash
python cli.py fetch          # загрузка источников
python cli.py parse          # парсинг
python cli.py enrich         # DNS + GeoIP
python cli.py filter         # фильтрация
python cli.py profile        # профилирование
python cli.py repack         # генерация out/
python cli.py build-subs     # EU-подписки
python cli.py report         # markdown-отчёт
python cli.py full           # полный пайплайн
```

Промежуточные результаты кэшируются в `.cache/` через pickle.

### 4. Вынесены встроенные URLs
**Файл:** `scripts/builtin_sources.py`

237 встроенных URLs вынесены из pipeline.py в отдельный модуль `BUILTIN_URLS`.

### 5. Рефакторинг pipeline.py
- Импорт `BUILTIN_URLS` из `scripts/builtin_sources.py`
- Удалён захардкоженный список из 237 URLs (строки 61-236)
- Код стал чище и короче

---

## 📊 Метрики

**До рефакторинга:**
- `pipeline.py`: 549 строк (237 строк — встроенные URLs)
- Дублирование констант в 3+ файлах
- Нет валидации конфига
- Невозможно запустить отдельные шаги

**После рефакторинга:**
- `pipeline.py`: ~370 строк (↓33%)
- `cli.py`: 180 строк (новый)
- `scripts/constants.py`: 90 строк (новый)
- `scripts/config_loader.py`: 150 строк (новый)
- `scripts/builtin_sources.py`: 170 строк (новый)
- Все константы в одном месте
- Валидация через Pydantic
- Модульный запуск через CLI

---

## 🎯 Следующие шаги (Фаза 2)

### Оптимизация производительности
1. **Async HTTP fetching** — aiohttp вместо requests
2. **Async DNS + GeoIP** — aiodns, batch processing
3. **Инкрементальные обновления** — кэширование хешей источников

### Улучшение качества данных
4. **Provider hunter** — определение первоисточников
5. **Alive checker** — отдельный модуль с async TCP ping
6. **Умный repacker** — применение format_template из конфига

### Персистентность
7. **SQLite для истории** — трекинг метрик во времени
8. **Автоматический whitelist/blacklist** — на основе score

---

## 🔧 Использование

### Запуск полного пайплайна
```bash
python pipeline.py
# или
python cli.py full
```

### Запуск отдельных шагов
```bash
python cli.py fetch
python cli.py parse
python cli.py enrich
python cli.py filter
python cli.py repack
```

### Проверка синтаксиса
```bash
python -m py_compile pipeline.py cli.py scripts/*.py
```

---

## 📝 Совместимость

Все изменения **обратно совместимы**:
- `pipeline.py` работает как раньше
- `config.yaml` не требует изменений
- Все существующие скрипты работают без модификаций
