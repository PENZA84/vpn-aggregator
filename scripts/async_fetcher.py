"""
Async HTTP fetcher с rate limiting и retry.
Заменяет синхронный requests на aiohttp для параллельной загрузки источников.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional
import time

import aiohttp


@dataclass
class FetchResult:
    """Результат загрузки одного источника."""
    name: str
    url: str
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class FetcherConfig:
    """Конфигурация async fetcher."""
    max_concurrent: int = 20  # максимум параллельных запросов
    timeout: int = 10  # таймаут на один запрос (секунды)
    max_retries: int = 3  # количество попыток
    retry_delay: float = 1.0  # начальная задержка между попытками (секунды)
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class AsyncFetcher:
    """
    Асинхронный загрузчик источников с:
    - Rate limiting через semaphore
    - Retry с exponential backoff
    - Graceful error handling
    """

    def __init__(self, config: Optional[FetcherConfig] = None):
        self.config = config or FetcherConfig()
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent)

    async def fetch_one(
        self,
        session: aiohttp.ClientSession,
        name: str,
        url: str,
    ) -> FetchResult:
        """
        Загружает один источник с retry.
        """
        async with self.semaphore:  # rate limiting
            start_time = time.monotonic()

            for attempt in range(self.config.max_retries):
                try:
                    timeout = aiohttp.ClientTimeout(total=self.config.timeout)
                    async with session.get(url, timeout=timeout) as resp:
                        resp.raise_for_status()
                        content = await resp.text()

                        duration_ms = int((time.monotonic() - start_time) * 1000)
                        return FetchResult(
                            name=name,
                            url=url,
                            success=True,
                            content=content,
                            duration_ms=duration_ms,
                        )

                except asyncio.TimeoutError:
                    error = f"Timeout after {self.config.timeout}s"
                except aiohttp.ClientError as exc:
                    error = f"HTTP error: {exc}"
                except Exception as exc:
                    error = f"Unexpected error: {exc}"

                # Retry с exponential backoff
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

            # Все попытки исчерпаны
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return FetchResult(
                name=name,
                url=url,
                success=False,
                error=error,
                duration_ms=duration_ms,
            )

    async def fetch_all(
        self,
        sources: List[Dict[str, str]],
    ) -> List[FetchResult]:
        """
        Загружает все источники параллельно.

        Args:
            sources: список dict с ключами 'name' и 'url'

        Returns:
            список FetchResult
        """
        headers = {"User-Agent": self.config.user_agent}
        connector = aiohttp.TCPConnector(limit=self.config.max_concurrent)

        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            tasks = [
                self.fetch_one(session, src["name"], src["url"])
                for src in sources
            ]
            results = await asyncio.gather(*tasks, return_exceptions=False)

        return results

    def fetch_all_sync(self, sources: List[Dict[str, str]]) -> List[FetchResult]:
        """
        Синхронная обёртка для fetch_all (для совместимости со старым кодом).
        """
        return asyncio.run(self.fetch_all(sources))


# ── Удобная функция для быстрого использования ────────────────────


async def fetch_sources_async(
    sources: List[Dict[str, str]],
    config: Optional[FetcherConfig] = None,
) -> List[FetchResult]:
    """
    Загружает список источников асинхронно.

    Args:
        sources: список dict с ключами 'name' и 'url'
        config: опциональная конфигурация

    Returns:
        список FetchResult
    """
    fetcher = AsyncFetcher(config)
    return await fetcher.fetch_all(sources)


def fetch_sources_sync(
    sources: List[Dict[str, str]],
    config: Optional[FetcherConfig] = None,
) -> List[FetchResult]:
    """
    Загружает список источников синхронно (блокирующий вызов).

    Args:
        sources: список dict с ключами 'name' и 'url'
        config: опциональная конфигурация

    Returns:
        список FetchResult
    """
    fetcher = AsyncFetcher(config)
    return fetcher.fetch_all_sync(sources)
