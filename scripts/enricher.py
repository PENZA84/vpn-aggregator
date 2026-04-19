"""
Enricher:
- DNS resolve (host -> ip)
- GeoIP (country, asn) через локальные MaxMind-базы
- Alive/ping через TCP connect (по умолчанию выключен для стабильности Actions)
"""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import geoip2.database

from .parser import VPNNode
from .constants import (
    DEFAULT_DNS_TIMEOUT,
    DEFAULT_PING_TIMEOUT,
    DEFAULT_MAX_NODES_PER_RUN,
    DEFAULT_DATA_DIR,
    GEOIP_COUNTRY_DB,
    GEOIP_ASN_DB,
)


@dataclass
class EnricherConfig:
    dns_timeout: float = DEFAULT_DNS_TIMEOUT

    enable_dns: bool = True
    enable_geoip: bool = True
    # ВАЖНО: по умолчанию ping выключен, чтобы Actions не висел
    enable_alive: bool = False

    # каталог и имена локальных GeoIP-баз
    db_dir: str = DEFAULT_DATA_DIR
    country_db_filename: str = GEOIP_COUNTRY_DB
    asn_db_filename: str = GEOIP_ASN_DB

    # лимит на количество нод для энричмента за один прогон
    # 0 = без лимита (по всем нодам)
    max_nodes_per_run: int = DEFAULT_MAX_NODES_PER_RUN

    # таймаут TCP-ping
    ping_timeout: float = DEFAULT_PING_TIMEOUT


class Enricher:
    def __init__(self, config: Optional[EnricherConfig] = None, debug: bool = False):
        self.config = config or EnricherConfig()
        self.debug = debug

        # Настройки под CI: агрессивный лимит и отключенный ping
        if os.environ.get("CI"):
            if self.config.max_nodes_per_run <= 0:
                self.config.max_nodes_per_run = 3000  # GeoIP только по верхним 3000 нод
            if self.config.dns_timeout > 2.0:
                self.config.dns_timeout = 2.0
            self.config.enable_alive = False

        if self.config.dns_timeout:
            socket.setdefaulttimeout(self.config.dns_timeout)

        self.db_dir = Path(self.config.db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.country_db_path = self.db_dir / self.config.country_db_filename
        self.asn_db_path = self.db_dir / self.config.asn_db_filename

        self._geo_country: Optional[geoip2.database.Reader] = None
        self._geo_asn: Optional[geoip2.database.Reader] = None

        if self.config.enable_geoip:
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

    def enrich_all(self, nodes: List[VPNNode]) -> None:
        """Массовое обогащение нод (DNS + GeoIP + ping)."""
        max_n = self.config.max_nodes_per_run or len(nodes)
        for i, node in enumerate(nodes):
            if i >= max_n:
                break
            if self.debug and i % 500 == 0:
                print(f"      [Enrich] {i}/{max_n}", flush=True)
            self._enrich_node(node)

    def _enrich_node(self, node: VPNNode) -> None:
        extra = node.extra

        # DNS resolve
        if self.config.enable_dns and "ip" not in extra:
            ip = self._resolve_ip(node.host)
            if ip:
                extra["ip"] = ip
                if self.debug:
                    print(f"      [DNS] {node.host} -> {ip}")

        ip = extra.get("ip")
        if not ip:
            return

        # GeoIP: country + ASN
        if self.config.enable_geoip:
            if self._geo_country:
                try:
                    c = self._geo_country.country(ip)
                    extra["country"] = c.country.iso_code or "XX"
                except Exception:
                    extra.setdefault("country", "XX")

            if self._geo_asn:
                try:
                    a = self._geo_asn.asn(ip)
                    extra["asn"] = a.autonomous_system_number
                    extra["asn_name"] = a.autonomous_system_organization
                except Exception:
                    extra.setdefault("asn", None)

        # Alive / ping через TCP connect (по умолчанию выключено)
        if self.config.enable_alive:
            ping_ms = self._tcp_ping(ip or node.host, node.port, timeout=self.config.ping_timeout)
            if ping_ms is None:
                extra["alive"] = False
                extra["ping"] = None
            else:
                extra["alive"] = True
                extra["ping"] = int(ping_ms)

    def _resolve_ip(self, host: str) -> Optional[str]:
        try:
            return socket.gethostbyname(host)
        except Exception:
            return None

    def _tcp_ping(self, host: str, port: int, timeout: float = 1.0) -> Optional[float]:
        """Простой TCP 'ping' — время установления TCP-соединения в мс."""
        try:
            start = time.monotonic()
            with socket.create_connection((host, port), timeout=timeout):
                end = time.monotonic()
            return (end - start) * 1000.0
        except Exception:
            return None

