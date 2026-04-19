#!/usr/bin/env python3
"""
CLI для VPN Aggregator.
Разбивает монолитный pipeline.py на отдельные команды.

Usage:
    python cli.py full              # полный пайплайн (все шаги)
    python cli.py fetch             # только загрузка источников
    python cli.py parse             # парсинг sources_raw/
    python cli.py enrich            # DNS + GeoIP enrichment
    python cli.py filter            # применение фильтров
    python cli.py profile           # построение профилей
    python cli.py repack            # генерация out/
    python cli.py report            # markdown-отчёт
    python cli.py build-subs        # EU-подписки
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.config_loader import load_config
from scripts.parser import ConfigParser
from scripts.enricher import Enricher
from scripts.filters import NodeFilter
from scripts.profiler import Profiler
from scripts.repacker import Repacker
from scripts.reporter import Reporter


def cmd_fetch(args):
    """Загрузка источников → sources_raw/"""
    from pipeline import ingest_sources

    config = load_config(args.config)
    cfg_dict = config.model_dump()

    print(">>> [fetch] Downloading sources...")
    ingest_sources(cfg_dict)
    print(">>> [fetch] Done")


def cmd_parse(args):
    """Парсинг sources_raw/ → VPNNode[]"""
    from pipeline import parse_sources, SOURCES_RAW_DIR

    print(">>> [parse] Parsing sources_raw/...")
    parser = ConfigParser()
    nodes = parse_sources(parser)
    print(f">>> [parse] Parsed {len(nodes)} nodes")

    # Сохраняем в промежуточный файл для следующих команд
    import pickle
    cache_dir = Path(".cache")
    cache_dir.mkdir(exist_ok=True)
    with open(cache_dir / "nodes_parsed.pkl", "wb") as f:
        pickle.dump(nodes, f)
    print(f">>> [parse] Cached to .cache/nodes_parsed.pkl")


def cmd_enrich(args):
    """DNS + GeoIP enrichment"""
    from pipeline import enrich_nodes_dns_geoip
    import pickle

    cache_file = Path(".cache/nodes_parsed.pkl")
    if not cache_file.exists():
        print("❌ Run 'parse' command first")
        return 1

    with open(cache_file, "rb") as f:
        nodes = pickle.load(f)

    print(f">>> [enrich] Enriching {len(nodes)} nodes...")
    enrich_nodes_dns_geoip(nodes)

    # Сохраняем обогащённые ноды
    with open(Path(".cache/nodes_enriched.pkl"), "wb") as f:
        pickle.dump(nodes, f)
    print(">>> [enrich] Done, cached to .cache/nodes_enriched.pkl")


def cmd_filter(args):
    """Применение фильтров"""
    from pipeline import apply_filters
    import pickle

    cache_file = Path(".cache/nodes_enriched.pkl")
    if not cache_file.exists():
        print("❌ Run 'enrich' command first")
        return 1

    with open(cache_file, "rb") as f:
        nodes = pickle.load(f)

    config = load_config(args.config)
    cfg_dict = config.model_dump()

    print(f">>> [filter] Filtering {len(nodes)} nodes...")
    filtered, stats = apply_filters(cfg_dict, nodes)
    print(f">>> [filter] After filters: {len(filtered)} nodes")

    with open(Path(".cache/nodes_filtered.pkl"), "wb") as f:
        pickle.dump((filtered, stats), f)
    print(">>> [filter] Done, cached to .cache/nodes_filtered.pkl")


def cmd_profile(args):
    """Построение профилей источников"""
    from pipeline import build_profiles
    import pickle

    cache_file = Path(".cache/nodes_filtered.pkl")
    if not cache_file.exists():
        print("❌ Run 'filter' command first")
        return 1

    with open(cache_file, "rb") as f:
        filtered, stats = pickle.load(f)

    config = load_config(args.config)
    cfg_dict = config.model_dump()

    print(f">>> [profile] Building profiles for {len(filtered)} nodes...")
    profiles = build_profiles(cfg_dict, filtered)
    print(f">>> [profile] Done")


def cmd_repack(args):
    """Генерация out/by_type, out/by_country"""
    from pipeline import repack_outputs
    import pickle

    cache_file = Path(".cache/nodes_filtered.pkl")
    if not cache_file.exists():
        print("❌ Run 'filter' command first")
        return 1

    with open(cache_file, "rb") as f:
        filtered, stats = pickle.load(f)

    config = load_config(args.config)
    cfg_dict = config.model_dump()

    print(f">>> [repack] Repacking {len(filtered)} nodes...")
    repack_outputs(cfg_dict, filtered)
    print(">>> [repack] Done")


def cmd_build_subs(args):
    """Генерация EU-подписок"""
    from pipeline import build_eu_subscriptions

    print(">>> [build-subs] Building EU subscriptions...")
    build_eu_subscriptions()
    print(">>> [build-subs] Done")


def cmd_report(args):
    """Генерация markdown-отчёта"""
    import pickle
    from pathlib import Path

    cache_file = Path(".cache/nodes_filtered.pkl")
    if not cache_file.exists():
        print("❌ Run 'filter' command first")
        return 1

    with open(cache_file, "rb") as f:
        filtered, stats = pickle.load(f)

    # Загружаем профили из JSON
    import json
    profiles_dir = Path("sources_meta/profiles")
    source_profiles = {}
    if profiles_dir.exists():
        for p in profiles_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                source_profiles[data.get("id", p.stem)] = data
            except Exception:
                pass

    print(">>> [report] Generating report...")
    reporter = Reporter()
    reporter.generate(
        nodes_raw=stats.get("before", 0),
        nodes_final=filtered,
        filter_stats=stats,
        source_profiles=source_profiles,
    )
    print(">>> [report] Done → sources_meta/pipeline_report.md")


def cmd_full(args):
    """Полный пайплайн (все шаги)"""
    print(">>> [full] Running full pipeline...")

    # Импортируем main из pipeline.py
    from pipeline import main as pipeline_main

    pipeline_main()
    print(">>> [full] Pipeline completed")


def main():
    parser = argparse.ArgumentParser(
        description="VPN Aggregator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Команды
    subparsers.add_parser("fetch", help="Download sources → sources_raw/")
    subparsers.add_parser("parse", help="Parse sources_raw/ → VPNNode[]")
    subparsers.add_parser("enrich", help="DNS + GeoIP enrichment")
    subparsers.add_parser("filter", help="Apply filters (dedup + geo + perf)")
    subparsers.add_parser("profile", help="Build source/provider profiles")
    subparsers.add_parser("repack", help="Generate out/by_type, out/by_country")
    subparsers.add_parser("build-subs", help="Generate EU subscriptions")
    subparsers.add_parser("report", help="Generate markdown report")
    subparsers.add_parser("full", help="Run full pipeline (all steps)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "fetch": cmd_fetch,
        "parse": cmd_parse,
        "enrich": cmd_enrich,
        "filter": cmd_filter,
        "profile": cmd_profile,
        "repack": cmd_repack,
        "build-subs": cmd_build_subs,
        "report": cmd_report,
        "full": cmd_full,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args) or 0
    else:
        print(f"❌ Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
