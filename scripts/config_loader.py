"""
Config loader с валидацией через Pydantic.
Читает config.yaml, мержит с дефолтами, валидирует структуру.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml
from pydantic import BaseModel, Field, field_validator

from .constants import (
    DEFAULT_EXCLUDE_COUNTRIES,
    DEFAULT_DNS_TIMEOUT,
    DEFAULT_PING_TIMEOUT,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_MAX_NODES_PER_RUN,
    DEFAULT_MIN_NODES_PER_SOURCE,
    DEFAULT_OUT_DIR,
    DEFAULT_DATA_DIR,
)


# ── Pydantic модели ───────────────────────────────────────────────


class AppConfig(BaseModel):
    name: str = "VPN Aggregator"
    version: str = "1.0.0"
    brand_name: str = "@мойканал"
    debug: bool = False


class GeoFilterConfig(BaseModel):
    eu_only: bool = True
    exclude_countries: List[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE_COUNTRIES))
    whitelist_countries: Optional[List[str]] = None


class PerformanceFilterConfig(BaseModel):
    min_alive_ratio: float = 0.6
    min_ping_ms: Optional[int] = None
    max_ping_ms: Optional[int] = 500


class FiltersConfig(BaseModel):
    geo: GeoFilterConfig = Field(default_factory=GeoFilterConfig)
    performance: PerformanceFilterConfig = Field(default_factory=PerformanceFilterConfig)
    asn_blacklist: List[int] = Field(default_factory=list)


class QualityMetricsConfig(BaseModel):
    profile_update_interval_hours: int = 24
    min_nodes_per_source: int = DEFAULT_MIN_NODES_PER_SOURCE


class OutputConfig(BaseModel):
    base_path: str = DEFAULT_OUT_DIR
    format_template: str = "{country} {ping}ms AS{asn} {protocol}"
    split_by_country: bool = True
    split_by_type: bool = True
    repack: Dict[str, Any] = Field(
        default_factory=lambda: {
            "preserve_fields": ["uuid", "password", "port", "host"],
            "modify_fields": ["remark", "tag", "group"],
        }
    )


class EncodingConfig(BaseModel):
    output_format: str = "base64"


class SourceEntry(BaseModel):
    name: str
    url: str
    enabled: bool = True


class SourcesConfig(BaseModel):
    ru_whitelists: List[SourceEntry] = Field(default_factory=list)
    global_mixed: List[SourceEntry] = Field(default_factory=list)
    iran_specific: List[SourceEntry] = Field(default_factory=list)
    collectors_subs: List[SourceEntry] = Field(default_factory=list)
    mirror_url_list: List[SourceEntry] = Field(default_factory=list)


class EnricherConfig(BaseModel):
    dns_timeout: float = DEFAULT_DNS_TIMEOUT
    ping_timeout: float = DEFAULT_PING_TIMEOUT
    http_timeout: int = DEFAULT_HTTP_TIMEOUT
    enable_dns: bool = True
    enable_geoip: bool = True
    enable_alive: bool = False
    max_nodes_per_run: int = DEFAULT_MAX_NODES_PER_RUN
    db_dir: str = DEFAULT_DATA_DIR
    country_db_filename: str = "GeoLite2-Country.mmdb"
    asn_db_filename: str = "GeoLite2-ASN.mmdb"


class Config(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    quality_metrics: QualityMetricsConfig = Field(default_factory=QualityMetricsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    encoding: EncodingConfig = Field(default_factory=EncodingConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    enricher: EnricherConfig = Field(default_factory=EnricherConfig)

    @field_validator("filters", mode="before")
    @classmethod
    def ensure_filters(cls, v):
        if v is None:
            return {}
        return v


# ── Loader ────────────────────────────────────────────────────────


class ConfigLoader:
    """Загрузчик конфигурации с валидацией и мержем дефолтов."""

    @staticmethod
    def load(path: str | Path = "config.yaml") -> Config:
        """
        Загружает config.yaml, мержит с дефолтами, валидирует через Pydantic.
        Если файл не найден — возвращает дефолтный конфиг.
        """
        path = Path(path)

        if not path.exists():
            print(f"⚠️  Config file {path} not found, using defaults")
            return Config()

        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            print(f"❌ Error parsing {path}: {exc}")
            print("   Using default config")
            return Config()

        try:
            config = Config(**raw)
            return config
        except Exception as exc:
            print(f"❌ Config validation error: {exc}")
            print("   Using default config")
            return Config()

    @staticmethod
    def to_dict(config: Config) -> Dict:
        """Конвертирует Pydantic-модель обратно в dict (для совместимости со старым кодом)."""
        return config.model_dump()


# ── Удобная функция для быстрого доступа ──────────────────────────


def load_config(path: str | Path = "config.yaml") -> Config:
    """Shortcut для загрузки конфига."""
    return ConfigLoader.load(path)
