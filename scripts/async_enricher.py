"""
Async Enricher с batch processing.
Улучшенная версия enricher.py с поддержкой async DNS и параллельной обработки.
"""

from __future__ import annotations

import os
import asyncio
from pathlib import Path
from typing import List, Optional

import geoip2.database

from .parser import VPNNode
from .async_dns import AsyncDNSResolver
from .constants import (
    DEFAULT_DNS_TIMEOUT,
    DEFAULT_PING_TIMEOUT,
    DEFAULT_MAX_NODES_PER_RUN,
    DEFAULT_DATA_DIR,
    GEOIP_COUNTRY_DB,
    GEOIP_ASN_DB,
)


class AsyncEnricher:
    """
    Асинхронный enricher с batch processing.

    Улучшения по сравнению с оригинальным Enricher:
    - Async DNS через AsyncDNSResolver
    - Batch processing по 100 нод за раз
    - Кэширование DNS результатов
    - Более эффективное использование GeoIP баз
    """

    def __init__(
        self,
        enable_dns: bool = True,
        enable_geoip: bool = True,
        enable_alive: bool = False,
        dns_timeout: float = DEFAULT_DNS_TIMEOUT,
        ping_timeout: float = DEFAULT_PING_TIMEOUT,
        max_nodes_per_run: int = DEFAULT_MAX_NODES_PER_RUN,
        db_dir: str = DEFAULT_DATA_DIR,
        batch_size: int = 100,
        debug: bool = False,
    ):
        self.enable_dns = enable_dns
        self.enable_geoip = enable_geoip
        self.enable_alive = enable_alive
        self.dns_timeout = dns_timeout
        self.ping_timeout = ping_timeout
        self.max_nodes_per_run = max_nodes_per_run
        self.batch_size = batch_size
        self.debug = debug

        # Настройки под CI
        if os.environ.get("CI"):
            if self.max_nodes_per_run <= 0:
                self.max_nodes_per_run = 3000
            self.enable_alive = False

        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.country_db_path = self.db_dir / GEOIP_COUNTRY_DB
        self.asn_db_path = self.db_dir / GEOIP_ASN_DB

        self._geo_country: Optional[geoip2.database.Reader] = None
        self._geo_asn: Optional[geoip2.database.Reader] = None

        # Загружаем GeoIP базы
        if self.enable_geoip:
            self._load_geoip_dbs()

        # DNS resolver
        self.dns_resolver = AsyncDNSResolver(
            timeout=self.dns_timeout,
            max_concurrent=50,
        ) if self.enable_dns else None

    def _load_geoip_dbs(self) -> None:
        """Загружает GeoIP базы."""
        if self.country_db_path.exists():
            try:
                self._geo_country = geoip2.database.Reader(str(self.country_db_path))
                if self.debug:
                    print(f"      [GeoIP] country DB loaded from {self.country_db_path}")
            except Exception as exc:
                if self.debug:
                    print(f"      [GeoIP] failed to open country DB: {exc}")
        else:
            if self.debug:
                print(f"      [GeoIP] country DB not found at {self.country_db_path}")

        if self.asn_db_path.exists():
            try:
                self._geo_asn = geoip2.database.Reader(str(self.asn_db_path))
                if self.debug:
                    print(f"      [GeoIP] ASN DB loaded from {self.asn_db_path}")
            except Exception as exc:
                if self.debug:
                    print(f"      [GeoIP] failed to open ASN DB: {exc}")
        else:
            if self.debug:
                print(f"      [GeoIP] ASN DB not found at {self.asn_db_path}")

    async def _enrich_batch_async(self, nodes: List[VPNNode]) -> None:
        """
        Обогащает батч нод асинхронно.
        """
        if not nodes:
            return

        # 1. DNS resolve для всех хостов без IP
        if self.enable_dns and self.dns_resolver:
            hosts_to_resolve = [
                n.host for n in nodes
                if "ip" not in n.extra and n.host
            ]

            if hosts_to_resolve:
                dns_results = await self.dns_resolver.resolve_batch(hosts_to_resolve)
                dns_map = {r.host: r.ip for r in dns_results if r.success and r.ip}

                # Применяем результаты DNS
                for node in nodes:
                    if "ip" not in node.extra and node.host in dns_map:
                        node.extra["ip"] = dns_map[node.host]

        # 2. GeoIP lookup (синхронный, но быстрый)
        if self.enable_geoip:
            for node in nodes:
                ip = node.extra.get("ip")
                if not ip:
                    continue

                # Country
                if self._geo_country:
                    try:
                        c = self._geo_country.country(ip)
                        node.extra["country"] = c.country.iso_code or "XX"
                    except Exception:
                        node.extra.setdefault("country", "XX")

                # ASN
                if self._geo_asn:
                    try:
                        a = self._geo_asn.asn(ip)
                        node.extra["asn"] = a.autonomous_system_number
                        node.extra["asn_name"] = a.autonomous_system_organization
                    except Exception:
                        node.extra.setdefault("asn", None)

    def enrich_all(self, nodes: List[VPNNode]) -> None:
        """
        Обогащает все ноды (синхронная обёртка).
        """
        max_n = self.max_nodes_per_run or len(nodes)
        nodes_to_process = nodes[:max_n]

        # Обрабатываем батчами
        for i in range(0, len(nodes_to_process), self.batch_size):
            batch = nodes_to_process[i:i + self.batch_size]

            if self.debug and i % 500 == 0:
                print(f"      [Enrich] {i}/{len(nodes_to_process)}", flush=True)

            # Запускаем async обработку батча
            asyncio.run(self._enrich_batch_async(batch))

    def get_dns_cache_stats(self) -> dict:
        """Статистика DNS кэша."""
        if self.dns_resolver:
            return self.dns_resolver.get_cache_stats()
        return {}
