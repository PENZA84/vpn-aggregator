#!/usr/bin/env python3
"""
VPN pipeline под CI (боевой с GeoIP):

  1. load_config  — читаем config.yaml
  2. ingest       — качаем источники → sources_raw/*.txt
  3. parse        — парсим в VPNNode[]
  4. enrich       — DNS + GeoIP (country+ASN), с лимитом в CI
  5. filter       — применяем NodeFilter из config.yaml
  6. profile      — строим профили по источникам и провайдерам
  7. repack       — генерим сабы в out/ по отфильтрованным нодам
  8. build_subs   — собираем EU-подписки и короткие ссылки в out/subscriptions_list.txt
  9. report       — собираем markdown-отчёт в sources_meta/pipeline_report.md
  10. status      — пишем краткий статус и GeoIP-сводку в out/status.txt
"""

from __future__ import annotations

import datetime
from collections import Counter
from pathlib import Path
from typing import List, Tuple

import requests
import yaml

from scripts.parser import ConfigParser, VPNNode
from scripts.enricher import Enricher, EnricherConfig
from scripts.filters import NodeFilter
from scripts.profiler import Profiler
from scripts.repacker import Repacker
from scripts.reporter import Reporter  # <-- добавили

SOURCES_RAW_DIR = Path("sources_raw")
OUT_DIR = Path("out")


def load_config(path: str = "config.yaml") -> dict:
    print(">>> [config] loading config.yaml", flush=True)
    try:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print("!!! config.yaml not found, using empty config", flush=True)
        return {}
    except yaml.YAMLError as exc:
        print(f"!!! error parsing config.yaml: {exc}", flush=True)
        return {}

    print(f">>> [config] sections: {list(cfg.keys())}", flush=True)
    return cfg


def ingest_sources(cfg: dict) -> None:
    print("\n[1/10] Ingesting sources...", flush=True)
    SOURCES_RAW_DIR.mkdir(parents=True, exist_ok=True)

    sources_cfg = cfg.get("sources", {}) or {}
    if not sources_cfg:
        print("    no sources in config", flush=True)
        return

    total_ok = total_fail = 0

    for group_name, group_list in sources_cfg.items():
        if not isinstance(group_list, list):
            continue
        print(f"    group: {group_name}", flush=True)

        for src in group_list:
            if not isinstance(src, dict) or not src.get("enabled", True):
                continue
            name = src.get("name") or "noname"
            url = (src.get("url") or "").strip()
            if not url:
                continue

            try:
                resp = requests.get(
                    url,
                    timeout=10,
                    headers={"User-Agent": "Mozilla/5.0"},
                    allow_redirects=True,
                )
                resp.raise_for_status()
                (SOURCES_RAW_DIR / f"{name}.txt").write_text(
                    resp.text, encoding="utf-8"
                )
                total_ok += 1
            except Exception as exc:
                print(f"      ✗ {name}: {exc}", flush=True)
                total_fail += 1

    print(f"    fetched: {total_ok}, failed: {total_fail}", flush=True)


def parse_sources(parser: ConfigParser) -> List[VPNNode]:
    print("\n[2/10] Parsing & normalising...", flush=True)
    if not SOURCES_RAW_DIR.exists():
        print("    sources_raw/ does not exist, nothing to parse", flush=True)
        return []

    all_nodes: List[VPNNode] = []
    total_raw = 0

    for path in sorted(SOURCES_RAW_DIR.glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            print(f"    ! Cannot read {path.name}: {exc}", flush=True)
            continue

        source_name = path.stem
        nodes = parser.parse_text(text, source=source_name)
        total_raw += len(text.splitlines())
        all_nodes.extend(nodes)
        print(f"      {path.name}: {len(nodes)} nodes", flush=True)

    print(
        f"    → raw lines: {total_raw}  nodes parsed: {len(all_nodes)}",
        flush=True,
    )
    return all_nodes


def enrich_nodes_dns_geoip(nodes: List[VPNNode]) -> Tuple[int, int]:
    print("\n[3/10] Enriching nodes (DNS + GeoIP)...", flush=True)
    if not nodes:
        print("    no nodes to enrich", flush=True)
        return 0, 0

    cfg = EnricherConfig()
    cfg.enable_dns = True
    cfg.enable_geoip = True
    cfg.enable_alive = False

    print(
        f"    enricher config: dns={cfg.enable_dns} geoip={cfg.enable_geoip} "
        f"alive={cfg.enable_alive} max_nodes_per_run={cfg.max_nodes_per_run}",
        flush=True,
    )

    enricher = Enricher(config=cfg, debug=False)
    enricher.enrich_all(nodes)

    with_ip = sum(1 for n in nodes if n.extra.get("ip"))
    with_country = sum(1 for n in nodes if n.extra.get("country"))
    print(
        f"    → nodes total: {len(nodes)}  with ip: {with_ip}  with country: {with_country}",
        flush=True,
    )
    return with_ip, with_country


def apply_filters(cfg: dict, nodes: List[VPNNode]) -> Tuple[List[VPNNode], dict]:
    print("\n[4/10] Applying filters...", flush=True)
    if not nodes:
        print("    no nodes to filter", flush=True)
        return nodes, {
            "before": 0,
            "after": 0,
            "dropped_dup": 0,
            "dropped_filter": 0,
        }

    node_filter = NodeFilter(cfg)
    filtered, stats = node_filter.apply(nodes)

    geo_cfg = cfg.get("filters", {}).get("geo", {}) or {}
    print(
        "    geo filter: "
        f"eu_only={geo_cfg.get('eu_only')} "
        f"exclude={geo_cfg.get('exclude_countries')} "
        f"whitelist={geo_cfg.get('whitelist_countries')}",
        flush=True,
    )

    print(
        f"    stats: before={stats.get('before')} "
        f"dup_dropped={stats.get('dropped_dup')} "
        f"filtered={stats.get('dropped_filter')} "
        f"after={stats.get('after')}",
        flush=True,
    )
    return filtered, stats


def build_profiles(cfg: dict, nodes: List[VPNNode]) -> dict:
    print("\n[5/10] Building profiles (sources + providers)...", flush=True)
    if not nodes:
        print("    no nodes to profile", flush=True)
        return {"by_source": {}, "by_provider": {}}

    quality = cfg.get("quality_metrics", {}) or {}
    min_nodes_per_source = quality.get("min_nodes_per_source", 5)

    profiler = Profiler(
        min_nodes=min_nodes_per_source,
        config=cfg,
    )
    profiles = profiler.build_profiles(nodes)

    by_source = profiles.get("by_source", {})
    by_provider = profiles.get("by_provider", {})

    print(
        f"    → source profiles: {len(by_source)} saved to sources_meta/profiles/",
        flush=True,
    )
    print(
        f"    → provider profiles: {len(by_provider)} saved to sources_meta/providers/",
        flush=True,
    )

    return profiles


def repack_outputs(cfg: dict, nodes: List[VPNNode]) -> None:
    print("\n[6/10] Repacking & generating outputs...", flush=True)
    if not nodes:
        print("    no nodes to repack", flush=True)
        return

    repacker = Repacker(cfg)
    repacker.repack(nodes)
    print("    → repack finished, out/ updated", flush=True)


def build_eu_subscriptions() -> None:
    """
    Шаг 8: генерация EU-подписок и списка коротких ссылок в out/subscriptions_list.txt.
    Ожидается, что в корне есть build_eu_subscriptions_list.py с функцией main().
    """
    try:
        from build_eu_subscriptions_list import main as build_eu_subs_main
    except ImportError as e:
        print("\n[7/10] build_eu_subscriptions_list.py not found or import error: {e}", flush=True)
        return

    print("\n[7/10] Building EU subscriptions list...", flush=True)
    try:
        rc = build_eu_subs_main()
        print(f"    → build_eu_subscriptions_list finished with code {rc}", flush=True)
    except Exception as e:
        print(f"    !!! error in build_eu_subscriptions_list: {e}", flush=True)


def collect_geoip_summary(nodes: List[VPNNode], top_n: int = 5) -> Tuple[str, str]:
    country_counter: Counter[str] = Counter()
    asn_counter: Counter[str] = Counter()

    for n in nodes:
        extra = n.extra or {}
        c = extra.get("country") or "XX"
        country_counter[c] += 1

        asn = extra.get("asn")
        asn_name = extra.get("asn_name")
        if asn:
            label = f"AS{asn} {asn_name}" if asn_name else f"AS{asn}"
            asn_counter[label] += 1

    top_countries = ", ".join(
        f"{c}:{cnt}" for c, cnt in country_counter.most_common(top_n)
    ) or "n/a"
    top_asn = ", ".join(
        f"{label}:{cnt}" for label, cnt in asn_counter.most_common(top_n)
    ) or "n/a"

    return top_countries, top_asn


def write_status(
    nodes_before: int,
    nodes_after: int,
    with_ip: int,
    with_country: int,
    sources_count: int,
    providers_count: int,
    top_countries: str,
    top_asn: str,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    status_file = OUT_DIR / "status.txt"
    now = datetime.datetime.utcnow().isoformat()
    status_file.write_text(
        f"Last run: {now}Z\n"
        f"Parsed nodes: {nodes_before}\n"
        f"With IP (after enrich): {with_ip}\n"
        f"With country (after GeoIP): {with_country}\n"
        f"After filters: {nodes_after}\n"
        f"Source profiles: {sources_count}\n"
        f"Provider profiles: {providers_count}\n"
        f"Top countries: {top_countries}\n"
        f"Top ASNs: {top_asn}\n",
        encoding="utf-8",
    )
    print("\n[10/10] wrote", status_file, flush=True)


def main() -> None:
    print(
        ">>> pipeline.py started (config + ingest + parse + enrich-geoip + filter + profile + repack + build_subs + report + status)",
        flush=True,
    )

    cfg = load_config()
    ingest_sources(cfg)

    parser = ConfigParser()
    nodes = parse_sources(parser)
    nodes_before = len(nodes)

    with_ip, with_country = enrich_nodes_dns_geoip(nodes)

    nodes_filtered, stats = apply_filters(cfg, nodes)
    nodes_after = len(nodes_filtered)

    profiles = build_profiles(cfg, nodes_filtered)
    sources_profiles = profiles.get("by_source", {}) or {}
    sources_count = len(sources_profiles)
    providers_count = len(profiles.get("by_provider", {}) or {})

    repack_outputs(cfg, nodes_filtered)

    # шаг 8: собираем EU-подписки и subscriptions_list.txt
    build_eu_subscriptions()

    # шаг 9: markdown-отчёт + список лучших источников
    print("\n[9/10] Generating pipeline report...", flush=True)
    reporter = Reporter()
    reporter.generate(
        nodes_raw=nodes_before,
        nodes_final=nodes_filtered,
        filter_stats=stats,
        source_profiles=sources_profiles,
    )

    top_countries, top_asn = collect_geoip_summary(nodes_filtered)

    write_status(
        nodes_before,
        nodes_after,
        with_ip,
        with_country,
        sources_count,
        providers_count,
        top_countries,
        top_asn,
    )

    print(">>> pipeline.py finished", flush=True)


if __name__ == "__main__":
    main()


