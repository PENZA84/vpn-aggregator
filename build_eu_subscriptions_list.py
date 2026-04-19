#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from scripts.constants import EU_COUNTRIES, KEYS_PER_SUBSCRIPTION

REPO_OWNER = "kort0881"
REPO_NAME = "vpn-aggregator"
BRANCH = "main"

BASE_OUT_BY_COUNTRY = Path("out/by_country")
SUBS_DIR = Path("out/subs")
SUBS_LIST_PATH = Path("out/subscriptions_list.txt")


def load_eu_keys() -> List[str]:
    """Берём URI из out/by_country/*.txt только для EU-стран."""
    keys: List[str] = []
    if not BASE_OUT_BY_COUNTRY.exists():
        print(f"⚠️ {BASE_OUT_BY_COUNTRY} не существует, запусти pipeline.py")
        return keys

    for cc in EU_COUNTRIES:
        path = BASE_OUT_BY_COUNTRY / f"{cc}.txt"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "://" not in line:
                continue
            keys.append(line)

    print(f"🌍 Найдено EU-ключей: {len(keys)}")
    return keys


def chunk_keys(keys: List[str], per_chunk: int) -> List[List[str]]:
    """Нарезает список ключей на чанки по per_chunk (1 чанк = 1 подписка)."""
    chunks: List[List[str]] = []
    for i in range(0, len(keys), per_chunk):
        part = keys[i:i + per_chunk]
        if part:
            chunks.append(part)
    return chunks


def build_raw_url(rel_path: str) -> str:
    """
    Делает RAW-URL для GitHub:
    out/subs/eu_sub_1.txt ->
    https://raw.githubusercontent.com/owner/repo/branch/out/subs/eu_sub_1.txt
    """
    return f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/{rel_path}"


def main() -> int:
    keys = load_eu_keys()
    if not keys:
        print("❌ Нет EU-ключей — подписки не создаём")
        return 1

    chunks = chunk_keys(keys, KEYS_PER_SUBSCRIPTION)
    print(f"📦 Подписок будет создано: {len(chunks)}")

    SUBS_DIR.mkdir(parents=True, exist_ok=True)

    sub_urls: List[str] = []

    for idx, sub_keys in enumerate(chunks, start=1):
        filename = f"eu_sub_{idx}.txt"
        rel_path = f"out/subs/{filename}"
        file_path = SUBS_DIR / filename

        # сохраняем ключи в файл
        file_path.write_text("\n".join(sub_keys) + "\n", encoding="utf-8")

        # формируем RAW-URL для этого файла
        url = build_raw_url(rel_path)
        sub_urls.append(url)

        print(f"  ✅ {filename}: {len(sub_keys)} ключей -> {url}")

    # Пишем список коротких ссылок на подписки
    SUBS_LIST_PATH.write_text("\n".join(sub_urls) + "\n", encoding="utf-8")
    print(f"\n📝 subscriptions_list.txt обновлён: {SUBS_LIST_PATH} ({len(sub_urls)} подписок)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
