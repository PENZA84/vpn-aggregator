"""
NodeFilter:
- dedup по (protocol, host, port, uuid/password)
- geo-фильтры из config.yaml (country / EU-only / blacklist / whitelist)
- performance-фильтры (ping, alive) + ASN blacklist
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .parser import VPNNode
from .constants import EU_COUNTRIES


@dataclass
class FilterStats:
    before: int = 0
    dropped_dup: int = 0
    dropped_filter: int = 0
    after: int = 0

    def to_dict(self) -> Dict:
        return {
            "before": self.before,
            "dropped_dup": self.dropped_dup,
            "dropped_filter": self.dropped_filter,
            "after": self.after,
        }


class NodeFilter:
    def __init__(self, config: Dict):
        self.config = config or {}

        filters_cfg = self.config.get("filters", {}) or {}
        self.geo_cfg = filters_cfg.get("geo", {}) or {}
        self.perf_cfg = filters_cfg.get("performance", {}) or {}
        self.asn_blacklist = set(filters_cfg.get("asn_blacklist", []) or [])

        # Используем константу из constants.py
        self.eu_countries = EU_COUNTRIES

    def apply(self, nodes: List[VPNNode]) -> Tuple[List[VPNNode], Dict]:
        """Применить dedup + geo/performance/ASN фильтры к списку нод."""
        stats = FilterStats()
        stats.before = len(nodes)

        # 1) dedup
        deduped = self._dedup(nodes)
        stats.dropped_dup = stats.before - len(deduped)

        # 2) geo/perf/asn фильтры
        filtered = self._apply_filters(deduped)
        stats.dropped_filter = len(deduped) - len(filtered)
        stats.after = len(filtered)

        return filtered, stats.to_dict()

    def _dedup(self, nodes: List[VPNNode]) -> List[VPNNode]:
        """Убираем дубли по (protocol, host, port, uuid/password)."""
        seen = set()
        result: List[VPNNode] = []

        for n in nodes:
            key = (
                n.protocol,
                n.host,
                n.port,
                n.uuid or n.password or "",
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(n)

        return result

    def _apply_filters(self, nodes: List[VPNNode]) -> List[VPNNode]:
        """Гео + производительность + ASN."""

        eu_only = self.geo_cfg.get("eu_only", False)
        exclude_countries = set(self.geo_cfg.get("exclude_countries", []) or [])
        whitelist_countries = set(self.geo_cfg.get("whitelist_countries") or [])

        min_ping = self.perf_cfg.get("min_ping_ms")
        max_ping = self.perf_cfg.get("max_ping_ms")

        result: List[VPNNode] = []

        for n in nodes:
            extra = n.extra

            country = extra.get("country")
            asn = extra.get("asn")
            ping = extra.get("ping")
            alive = extra.get("alive")

            # Geo: исключить страны
            if country and country in exclude_countries:
                continue

            # Geo: whitelist стран
            if whitelist_countries and country and country not in whitelist_countries:
                continue

            # Geo: только EU
            if eu_only and country:
                if country not in self.eu_countries:
                    continue

            # ASN blacklist
            if asn and asn in self.asn_blacklist:
                continue

            # Alive: если alive явно False — выкидываем
            if alive is False:
                continue

            # Performance: ping
            if isinstance(ping, (int, float)):
                if min_ping is not None and ping < min_ping:
                    continue
                if max_ping is not None and ping > max_ping:
                    continue

            result.append(n)

        return result

