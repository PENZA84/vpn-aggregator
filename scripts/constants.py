"""
Общие константы проекта.
Вынесены из filters.py, profiler.py, build_eu_subscriptions_list.py для единообразия.
"""

from typing import Set

# ── Географические константы ──────────────────────────────────────

EU_COUNTRIES: Set[str] = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE",
}

# Страны, которые считаются "плохими" для профилирования
BAD_COUNTRIES: Set[str] = {"RU", "BY", "IR", "CN", "KP"}

# Дефолтные исключения (можно переопределить в config.yaml)
DEFAULT_EXCLUDE_COUNTRIES: Set[str] = {"RU", "BY", "KZ", "CN", "IR"}

# ── Таймауты и лимиты ─────────────────────────────────────────────

DEFAULT_DNS_TIMEOUT: float = 2.0
DEFAULT_PING_TIMEOUT: float = 1.0
DEFAULT_HTTP_TIMEOUT: int = 10

# Лимит нод для enrichment в CI (0 = без лимита)
DEFAULT_MAX_NODES_PER_RUN: int = 3000

# ── Пути ──────────────────────────────────────────────────────────

DEFAULT_SOURCES_RAW_DIR: str = "sources_raw"
DEFAULT_OUT_DIR: str = "out"
DEFAULT_META_DIR: str = "sources_meta"
DEFAULT_DATA_DIR: str = "data"

# ── GeoIP базы ────────────────────────────────────────────────────

GEOIP_COUNTRY_DB: str = "GeoLite2-Country.mmdb"
GEOIP_ASN_DB: str = "GeoLite2-ASN.mmdb"

# ── Профилирование ────────────────────────────────────────────────

# Минимальное количество нод для создания профиля источника
DEFAULT_MIN_NODES_PER_SOURCE: int = 5

# Пороги для классификации источников
FIRST_PARTY_ASN_CONCENTRATION: float = 0.7  # 70%+ нод в одном ASN
FIRST_PARTY_IP_DIVERSITY: float = 0.4       # ≤40% уникальных IP

AGGREGATOR_MIN_ASN_DIVERSITY: int = 15      # ≥15 разных ASN
AGGREGATOR_MIN_IP_DIVERSITY: float = 0.75   # ≥75% уникальных IP

# ── Scoring ───────────────────────────────────────────────────────

# Веса для расчёта score источника
SCORE_WEIGHT_EU_SHARE: float = 2.0
SCORE_WEIGHT_BAD_SHARE: float = -3.0
SCORE_WEIGHT_ALIVE: float = 1.5
SCORE_WEIGHT_LOG_NODES: float = 0.2

# Штрафы
SCORE_PENALTY_FEW_IPS_THRESHOLD: int = 10
SCORE_PENALTY_FEW_IPS: float = 0.3
SCORE_PENALTY_MEDIUM_IPS_THRESHOLD: int = 50
SCORE_PENALTY_MEDIUM_IPS: float = 0.1

# ── Теги для whitelist/blacklist ──────────────────────────────────

# Пороги для тега whitelist_candidate
WHITELIST_MIN_EU_SHARE: float = 0.7
WHITELIST_MAX_BAD_SHARE: float = 0.1
WHITELIST_MIN_ALIVE_RATIO: float = 0.5

# Пороги для тега blacklist_candidate
BLACKLIST_MIN_BAD_SHARE: float = 0.5
BLACKLIST_MAX_ALIVE_RATIO: float = 0.1

# Пороги для тега large_source
LARGE_SOURCE_MIN_NODES: int = 500
LARGE_SOURCE_MIN_UNIQUE_IPS: int = 50

# ── Reporter ──────────────────────────────────────────────────────

# Минимальные требования для "хорошего источника" в отчёте
REPORTER_MIN_NODES: int = 500
REPORTER_MIN_UNIQUE_IPS: int = 50
REPORTER_TOP_N: int = 50

# ── Build EU subscriptions ────────────────────────────────────────

KEYS_PER_SUBSCRIPTION: int = 100
