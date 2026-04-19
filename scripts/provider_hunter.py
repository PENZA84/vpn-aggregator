"""
Provider Hunter — определение первоисточников VPN-конфигов.

Анализирует remark/ps поля для извлечения информации о провайдере:
- Telegram каналы (@channel)
- Домены (example.com)
- Известные провайдеры (V2rayNG, Clash, etc.)
- Географические метки
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Set
from urllib.parse import urlparse

from .parser import VPNNode


@dataclass
class ProviderInfo:
    """Информация о провайдере."""
    provider_id: str  # уникальный ID провайдера
    provider_type: str  # telegram, domain, app, unknown
    confidence: float  # уверенность в определении (0.0-1.0)
    raw_text: str  # исходный текст из remark
    metadata: Dict[str, str]  # дополнительные данные


class ProviderHunter:
    """
    Определяет первоисточник VPN-конфига по remark/ps полю.

    Стратегии:
    1. Telegram каналы: @channel, t.me/channel
    2. Домены: example.com, https://example.com
    3. Известные приложения: V2rayNG, Clash, Shadowrocket
    4. Географические метки: 🇺🇸, US, United States
    5. Fallback: хеш от remark
    """

    def __init__(self):
        # Regex паттерны для различных типов провайдеров
        self.telegram_pattern = re.compile(
            r'@([a-zA-Z0-9_]{5,32})|t\.me/([a-zA-Z0-9_]{5,32})|telegram\.me/([a-zA-Z0-9_]{5,32})',
            re.IGNORECASE
        )

        self.domain_pattern = re.compile(
            r'(?:https?://)?([a-zA-Z0-9][-a-zA-Z0-9]{0,62}(?:\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+)',
            re.IGNORECASE
        )

        # Известные приложения/сервисы
        self.known_apps = {
            'v2rayng', 'v2rayn', 'clash', 'shadowrocket', 'quantumult',
            'surge', 'kitsunebi', 'pharos', 'pepi', 'shadowsocks',
            'outline', 'v2fly', 'xray', 'sing-box'
        }

        # Известные публичные провайдеры
        self.known_providers = {
            'freevpn', 'vpngate', 'protonvpn', 'windscribe',
            'tunnelbear', 'hide.me', 'speedify'
        }

    def extract_provider(self, node: VPNNode) -> ProviderInfo:
        """
        Извлекает информацию о провайдере из ноды.
        """
        remark = node.remark.strip() if node.remark else ""

        if not remark:
            # Fallback: используем source_name
            source_name = node.extra.get("source_name", "unknown")
            return ProviderInfo(
                provider_id=source_name,
                provider_type="source",
                confidence=0.5,
                raw_text="",
                metadata={"source": source_name}
            )

        # 1. Проверяем Telegram
        tg_match = self.telegram_pattern.search(remark)
        if tg_match:
            channel = next(g for g in tg_match.groups() if g)
            return ProviderInfo(
                provider_id=f"tg_{channel.lower()}",
                provider_type="telegram",
                confidence=0.9,
                raw_text=remark,
                metadata={"channel": channel}
            )

        # 2. Проверяем домены
        domain_match = self.domain_pattern.search(remark)
        if domain_match:
            domain = domain_match.group(1).lower()
            # Фильтруем IP-адреса
            if not re.match(r'^\d+\.\d+\.\d+\.\d+$', domain):
                return ProviderInfo(
                    provider_id=f"domain_{domain}",
                    provider_type="domain",
                    confidence=0.8,
                    raw_text=remark,
                    metadata={"domain": domain}
                )

        # 3. Проверяем известные приложения
        remark_lower = remark.lower()
        for app in self.known_apps:
            if app in remark_lower:
                return ProviderInfo(
                    provider_id=f"app_{app}",
                    provider_type="app",
                    confidence=0.7,
                    raw_text=remark,
                    metadata={"app": app}
                )

        # 4. Проверяем известных провайдеров
        for provider in self.known_providers:
            if provider in remark_lower:
                return ProviderInfo(
                    provider_id=f"provider_{provider}",
                    provider_type="provider",
                    confidence=0.8,
                    raw_text=remark,
                    metadata={"provider": provider}
                )

        # 5. Fallback: хеш от remark
        remark_hash = str(abs(hash(remark)) % 10000000)
        return ProviderInfo(
            provider_id=f"remark_{remark_hash}",
            provider_type="unknown",
            confidence=0.3,
            raw_text=remark,
            metadata={"remark": remark[:50]}
        )

    def enrich_nodes(self, nodes: List[VPNNode]) -> None:
        """
        Обогащает список нод информацией о провайдерах.
        Добавляет в node.extra:
        - provider_id
        - provider_type
        - provider_confidence
        """
        for node in nodes:
            provider_info = self.extract_provider(node)
            node.extra["provider_id"] = provider_info.provider_id
            node.extra["provider_type"] = provider_info.provider_type
            node.extra["provider_confidence"] = provider_info.confidence
            node.extra["provider_metadata"] = provider_info.metadata

    def build_provider_graph(self, nodes: List[VPNNode]) -> Dict[str, Set[str]]:
        """
        Строит граф зависимостей: source -> providers.

        Returns:
            {source_name: {provider_id1, provider_id2, ...}}
        """
        graph: Dict[str, Set[str]] = {}

        for node in nodes:
            source = node.extra.get("source_name", "unknown")
            provider = node.extra.get("provider_id", "unknown")

            if source not in graph:
                graph[source] = set()
            graph[source].add(provider)

        return graph

    def get_provider_stats(self, nodes: List[VPNNode]) -> Dict[str, Dict]:
        """
        Статистика по провайдерам.

        Returns:
            {
                provider_id: {
                    "count": int,
                    "type": str,
                    "avg_confidence": float,
                    "sources": [source1, source2, ...]
                }
            }
        """
        stats: Dict[str, Dict] = {}

        for node in nodes:
            provider_id = node.extra.get("provider_id", "unknown")
            provider_type = node.extra.get("provider_type", "unknown")
            confidence = node.extra.get("provider_confidence", 0.0)
            source = node.extra.get("source_name", "unknown")

            if provider_id not in stats:
                stats[provider_id] = {
                    "count": 0,
                    "type": provider_type,
                    "confidences": [],
                    "sources": set(),
                }

            stats[provider_id]["count"] += 1
            stats[provider_id]["confidences"].append(confidence)
            stats[provider_id]["sources"].add(source)

        # Вычисляем средние значения
        for provider_id, data in stats.items():
            confidences = data.pop("confidences")
            data["avg_confidence"] = sum(confidences) / len(confidences) if confidences else 0.0
            data["sources"] = list(data["sources"])

        return stats


# ── Удобные функции ───────────────────────────────────────────────


def hunt_providers(nodes: List[VPNNode]) -> None:
    """
    Обогащает ноды информацией о провайдерах.
    """
    hunter = ProviderHunter()
    hunter.enrich_nodes(nodes)


def get_provider_stats(nodes: List[VPNNode]) -> Dict[str, Dict]:
    """
    Возвращает статистику по провайдерам.
    """
    hunter = ProviderHunter()
    return hunter.get_provider_stats(nodes)
