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
    def _fmt_ratio(x):
        if x is None:
            return "-"
        return f"{x:.2f}"

    @staticmethod
    def _compute_score(p: Dict) -> float:
        """Интегральный скор качества источника (можно подстроить под себя)."""
        alive = p.get("alive_ratio") or 0.0
        eu = p.get("eu_share") or 0.0
        bad = p.get("bad_country_share") or 0.0
        unique_ips = p.get("unique_ips") or 0
        avg_ping = p.get("avg_ping") or None

        # штраф за мало IP
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
        """Жёсткие пороги для попадания в список качественных источников."""
        alive = p.get("alive_ratio") or 0.0
        eu = p.get("eu_share") or 0.0
        bad = p.get("bad_country_share") or 0.0
        unique_ips = p.get("unique_ips") or 0

        if alive < 0.8:
            return False
        if eu < 0.9:
            return False
        if bad > 0.02:
            return False
        if unique_ips < 20:
            return False
        return True

    def _select_best_sources(
        self, source_profiles: Dict[str, Dict], top_n: int = 50
    ) -> List[Tuple[str, Dict]]:
        scored: List[Tuple[str, Dict]] = []
        for name, p in source_profiles.items():
            if not self._is_good_source(p):
                continue
            score = self._compute_score(p)
            p = dict(p)  # не портим оригинал
            p["score"] = score
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

        # Filter stats
        lines.append("## Filter stats")
        lines.append("")
        lines.append(f"- Before: `{filter_stats.get('before')}`")
        lines.append(f"- Dropped as duplicates: `{filter_stats.get('dropped_dup')}`")
        lines.append(
            f"- Dropped by filters: `{filter_stats.get('dropped_filter')}`"
        )
        lines.append(f"- After: `{filter_stats.get('after')}`")
        lines.append("")

        # Sources table
        lines.append("## Sources")
        lines.append("")
        if not source_profiles:
            lines.append("_No profiles available_")
        else:
            lines.append(
                "| Source | Nodes | EU share | Bad country share | "
                "Avg ping | Alive ratio | Unique IPs |"
            )
            lines.append(
                "|--------|-------|----------|-------------------|"
                "----------|-------------|-----------|"
            )
            for name, p in sorted(source_profiles.items()):
                nodes = p.get("total_nodes") or p.get("nodes")
                eu_share = p.get("eu_share")
                bad_share = p.get("bad_country_share")
                avg_ping = p.get("avg_ping")
                alive_ratio = p.get("alive_ratio")
                unique_ips = p.get("unique_ips")

                lines.append(
                    f"| `{name}` | {nodes} | "
                    f"{self._fmt_ratio(eu_share)} | "
                    f"{self._fmt_ratio(bad_share)} | "
                    f"{avg_ping if avg_ping is not None else '-'} | "
                    f"{self._fmt_ratio(alive_ratio)} | "
                    f"{unique_ips if unique_ips is not None else '-'} |"
                )

        # Блок с лучшими источниками
        lines.append("")
        lines.append("## Best sources (for reuse)")
        lines.append("")
        if not source_profiles:
            lines.append("_No profiles to rank_")
        else:
            best = self._select_best_sources(source_profiles, top_n=50)
            if not best:
                lines.append("_No sources passed quality thresholds_")
            else:
                # Таблица с топами
                lines.append(
                    "| Rank | Source | Score | Alive | EU share | "
                    "Bad share | Unique IPs |"
                )
                lines.append(
                    "|------|--------|-------|-------|----------|"
                    "-----------|-----------|"
                )
                for idx, (name, p) in enumerate(best, start=1):
                    lines.append(
                        f"| {idx} | `{name}` | "
                        f"{p['score']:.3f} | "
                        f"{self._fmt_ratio(p.get('alive_ratio'))} | "
                        f"{self._fmt_ratio(p.get('eu_share'))} | "
                        f"{self._fmt_ratio(p.get('bad_country_share'))} | "
                        f"{p.get('unique_ips') or '-'} |"
                    )

                # Внизу — простой список id, чтобы другие скрипты могли читать
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
