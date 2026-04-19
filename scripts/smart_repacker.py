"""
Smart Repacker — умная переупаковка конфигов с применением шаблонов.

Применяет настройки из config.yaml:
- format_template: шаблон для remark
- brand_name: брендирование
- preserve_fields: поля для сохранения
- modify_fields: поля для изменения
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import List, Dict

from .parser import VPNNode, ConfigParser


class SmartRepacker:
    """
    Умный repacker с поддержкой шаблонов и брендирования.

    Улучшения по сравнению с оригинальным Repacker:
    - Применяет format_template из конфига
    - Добавляет brand_name к remark
    - Учитывает preserve_fields и modify_fields
    - Генерирует человекочитаемые имена
    """

    def __init__(self, config: dict):
        self.config = config
        out_cfg = self.config.get("output", {}) or {}
        repack_cfg = out_cfg.get("repack", {}) or {}

        base_out = Path(out_cfg.get("base_path", "./out"))
        self.by_type_dir = base_out / "by_type"
        self.by_country_dir = base_out / "by_country"
        self.subs_dir = base_out / "subs"

        self.by_type_dir.mkdir(parents=True, exist_ok=True)
        self.by_country_dir.mkdir(parents=True, exist_ok=True)
        self.subs_dir.mkdir(parents=True, exist_ok=True)

        # Настройки из конфига
        app_cfg = self.config.get("app", {}) or {}
        self.brand_name = app_cfg.get("brand_name", "")
        self.format_template = out_cfg.get("format_template", "{country} {protocol}")
        self.preserve_fields = set(repack_cfg.get("preserve_fields", []))
        self.modify_fields = set(repack_cfg.get("modify_fields", ["remark", "tag", "group"]))

    def _format_remark(self, node: VPNNode) -> str:
        """
        Форматирует remark по шаблону из конфига.

        Доступные переменные:
        - {country}: код страны (DE, NL, ...)
        - {protocol}: тип протокола (vless, vmess, ss)
        - {ping}: ping в ms
        - {asn}: номер ASN
        - {asn_name}: название ASN
        - {brand}: brand_name из конфига
        """
        extra = node.extra or {}

        # Собираем данные для шаблона
        template_vars = {
            "country": extra.get("country", "XX"),
            "protocol": node.protocol.upper(),
            "ping": extra.get("ping", "?"),
            "asn": extra.get("asn", "?"),
            "asn_name": extra.get("asn_name", "Unknown"),
            "brand": self.brand_name,
            "host": node.host[:20],  # первые 20 символов хоста
            "port": node.port,
        }

        try:
            remark = self.format_template.format(**template_vars)
        except KeyError as e:
            # Если в шаблоне неизвестная переменная — используем дефолт
            remark = f"{template_vars['country']} {template_vars['protocol']}"

        # Добавляем brand_name в конец (если не в шаблоне)
        if self.brand_name and "{brand}" not in self.format_template:
            remark = f"{remark} {self.brand_name}"

        return remark.strip()

    def _rebuild_node(self, node: VPNNode) -> str:
        """
        Пересобирает URI ноды с новым remark.
        """
        # Если remark в modify_fields — применяем шаблон
        if "remark" in self.modify_fields:
            new_remark = self._format_remark(node)
        else:
            new_remark = node.remark

        # Используем ConfigParser для rebuild
        return ConfigParser.rebuild_uri(node, new_remark=new_remark)

    def repack(self, nodes: List[VPNNode]) -> None:
        """
        Переупаковывает ноды с применением шаблонов.
        """
        # Группировка по типу и стране
        by_type: Dict[str, List[str]] = defaultdict(list)
        by_country: Dict[str, List[str]] = defaultdict(list)

        for node in nodes:
            uri = self._rebuild_node(node)
            protocol = node.protocol
            by_type[protocol].append(uri)

            extra = node.extra or {}
            country = extra.get("country") or "XX"
            by_country[country].append(uri)

        # Запись по типам
        for protocol, lines in by_type.items():
            path = self.by_type_dir / f"{protocol}.txt"
            text = "\n".join(lines) + "\n"
            path.write_text(text, encoding="utf-8")
            print(f"    - by_type: {protocol} -> {path} ({len(lines)} lines)")

        # Запись по странам
        for country, lines in by_country.items():
            path = self.by_country_dir / f"{country}.txt"
            text = "\n".join(lines) + "\n"
            path.write_text(text, encoding="utf-8")
            print(f"    - by_country: {country} -> {path} ({len(lines)} lines)")

        # Саб-генерация
        for protocol, lines in by_type.items():
            sub_path = self.subs_dir / f"{protocol}_sub.txt"
            text = "\n".join(lines) + "\n"
            sub_path.write_text(text, encoding="utf-8")
            print(f"    - sub: {protocol} -> {sub_path} ({len(lines)} lines)")

    def get_stats(self, nodes: List[VPNNode]) -> Dict[str, int]:
        """
        Статистика по нодам для репака.
        """
        by_type: Dict[str, int] = defaultdict(int)
        by_country: Dict[str, int] = defaultdict(int)

        for node in nodes:
            by_type[node.protocol] += 1
            country = node.extra.get("country", "XX")
            by_country[country] += 1

        return {
            "total": len(nodes),
            "by_type": dict(by_type),
            "by_country": dict(by_country),
        }
