#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reporter:
- собирает markdown-отчёт по пайплайну
- сохраняет в sources_meta/pipeline_report.md
- в конце формирует человекочитаемый список лучших источников
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .parser import VPNNode


class Reporter:
    def __init__(self, out_path: str = "sources_meta/pipeline_report.md"):
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _fmt_ratio(x) -> str:
        if x is None:
            return "-"
        return f"{x:.2f}"

    @staticmethod
    def _compute_score(p: Dict) -> float:
        """Интегральный скор качества источника."""
        alive = p.get("alive_ratio") or 0.0
        eu = p.get("eu_share") or 0.0
        bad = p.get("bad_country_share") or 0.0
        unique_ips = p.get("unique_ips") or 0
        avg_ping = p.get("avg_ping") or None

        # штраф за мало уникальных IP
        penalty_ips = 0.0
        if unique_ips < 10:
            penalty_ips = 0.3
        elif unique_ips < 20:
            penalty_ips = 0.15

        # штраф за высокий ping (если есть)
        penalty_ping = 0.0
        if avg_ping is not None:
            if avg_ping > 800:
                penalty_ping = 0.3
            elif avg_ping > 500:
                penalty_ping = 0.15

        score = alive * 0.5 + eu * 0.3 - bad * 0.2 - penalty_ips - penalty_ping
        return max(score, 0.0)

    @staticmethod
    def _is_good_source(p: Dict) -> bool:
        """
        Мягкий отбор качественных источников пока только по размеру:
        - достаточно много нод с этого источника
        - достаточно разнообразных IP
        Остальные метрики (alive_ratio, eu_share, bad_country_share) влияют
        только на score, но не режут жёстко (пока alive-чекер не включён).
        """
        total_nodes = p.get("total_nodes") or p.get("nodes") or 0
        unique_ips = p.get("unique_ips") or 0

        if total_nodes < 500:
            return False
        if unique_ips < 50:
            return False

        return True

    def _select_best_sources(
        self, source_profiles: Dict[str, Dict], top_n: int = 50
    ) -> List[Tuple[str, Dict]]:
        scored: List[Tuple[str, Dict]] = []
        for name, p in source_profiles.items():
            if not self._is_good_source(p):
                continue
            p = dict(p)  # не портим оригинал
            p["score"] = self._compute_score(p)
            scored.append((name, p))

        scored.sort(key=lambda x: x[1]["score"], reverse=True)
        return scored[:top_n]

    def generate(
        self,
        nodes_raw: int,
        nodes_final: List[VPNNode],
        filter_stats: Dict,
        source_profiles: Dict[str, Dict],
    ) -> str:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        lines: List[str] = []

        lines.append("# VPN Aggregator Report")
        lines.append("")
        lines.append(f"- Generated at: **{ts}**")
        lines.append(f"- Raw nodes (lines before parse): **{nodes_raw}**")
        lines.append(f"- Final nodes after filters: **{len(nodes_final)}**")
        lines.append("")

        # ── Filter stats ──────────────────────────────────────────
        lines.append("## Filter stats")
        lines.append("")
        lines.append(f"- Before: `{filter_stats.get('before')}`")
        lines.append(f"- Dropped as duplicates: `{filter_stats.get('dropped_dup')}`")
        lines.append(f"- Dropped by filters: `{filter_stats.get('dropped_filter')}`")
        lines.append(f"- After: `{filter_stats.get('after')}`")
        lines.append("")

        # ── Sources table ─────────────────────────────────────────
        lines.append("## Sources")
        lines.append("")
        if not source_profiles:
            lines.append("_No profiles available_")
        else:
            lines.append(
                "| Source | Nodes | Unique IPs | EU share | Bad share | "
                "Avg ping | Alive ratio | Score | Type |"
            )
            lines.append(
                "|--------|-------|------------|----------|-----------|"
                "----------|-------------|-------|------|"
            )
            for name, p in sorted(
                source_profiles.items(),
                key=lambda x: x[1].get("score") or 0.0,
                reverse=True,
            ):
                total = p.get("total_nodes") or p.get("nodes") or "-"
                unique_ips = p.get("unique_ips")
                eu_share = p.get("eu_share")
                bad_share = p.get("bad_country_share")
                avg_ping = p.get("avg_ping")
                alive_ratio = p.get("alive_ratio")
                score = p.get("score")
                source_type = p.get("source_type") or "-"

                lines.append(
                    f"| `{name}` | {total} | "
                    f"{unique_ips if unique_ips is not None else '-'} | "
                    f"{self._fmt_ratio(eu_share)} | "
                    f"{self._fmt_ratio(bad_share)} | "
                    f"{avg_ping if avg_ping is not None else '-'} | "
                    f"{self._fmt_ratio(alive_ratio)} | "
                    f"{self._fmt_ratio(score)} | "
                    f"{source_type} |"
                )

        # ── Best sources ──────────────────────────────────────────
        lines.append("")
        lines.append("## Best sources (for reuse)")
        lines.append("")

        if not source_profiles:
            lines.append("_No profiles to rank_")
        else:
            best = self._select_best_sources(source_profiles, top_n=50)
            if not best:
                lines.append(
                    "_No sources passed quality thresholds "
                    "(min 500 nodes, min 50 unique IPs)_"
                )
            else:
                # таблица топов
                lines.append(
                    "| Rank | Source | Score | Nodes | Unique IPs | "
                    "EU share | Bad share | Alive | Type |"
                )
                lines.append(
                    "|------|--------|-------|-------|------------|"
                    "----------|-----------|-------|------|"
                )
                for idx, (name, p) in enumerate(best, start=1):
                    lines.append(
                        f"| {idx} | `{name}` | "
                        f"{p['score']:.3f} | "
                        f"{p.get('total_nodes') or '-'} | "
                        f"{p.get('unique_ips') or '-'} | "
                        f"{self._fmt_ratio(p.get('eu_share'))} | "
                        f"{self._fmt_ratio(p.get('bad_country_share'))} | "
                        f"{self._fmt_ratio(p.get('alive_ratio'))} | "
                        f"{p.get('source_type') or '-'} |"
                    )

                # список id — для парсинга в других скриптах
                lines.append("")
                lines.append("### Best source IDs")
                lines.append("")
                lines.append("```text")
                for name, _ in best:
                    lines.append(name)
                lines.append("```")

        report = "\n".join(lines) + "\n"
        self.out_path.write_text(report, encoding="utf-8")
        return report
