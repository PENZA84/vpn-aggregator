"""
Async DNS resolver с кэшированием.
Использует aiodns для неблокирующего DNS lookup.
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import Dict, Optional, List
import time

try:
    import aiodns
    AIODNS_AVAILABLE = True
except ImportError:
    AIODNS_AVAILABLE = False


@dataclass
class DNSResult:
    """Результат DNS lookup."""
    host: str
    ip: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    cached: bool = False


class AsyncDNSResolver:
    """
    Асинхронный DNS resolver с кэшированием.

    Особенности:
    - Использует aiodns для async lookup
    - Кэширует результаты в памяти
    - Batch processing для эффективности
    - Fallback на синхронный socket.gethostbyname если aiodns недоступен
    """

    def __init__(
        self,
        timeout: float = 2.0,
        cache_ttl: int = 3600,  # TTL кэша в секундах (1 час)
        max_concurrent: int = 50,
    ):
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.max_concurrent = max_concurrent

        # Кэш: {host: (ip, timestamp)}
        self._cache: Dict[str, tuple[str, float]] = {}

        # Semaphore для rate limiting
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # aiodns resolver (если доступен)
        self.resolver = aiodns.DNSResolver(timeout=timeout) if AIODNS_AVAILABLE else None

    def _get_from_cache(self, host: str) -> Optional[str]:
        """Получить IP из кэша, если не истёк TTL."""
        if host in self._cache:
            ip, timestamp = self._cache[host]
            if time.time() - timestamp < self.cache_ttl:
                return ip
            else:
                # Кэш истёк
                del self._cache[host]
        return None

    def _put_to_cache(self, host: str, ip: str) -> None:
        """Сохранить IP в кэш."""
        self._cache[host] = (ip, time.time())

    async def resolve_one(self, host: str) -> DNSResult:
        """
        Резолвит один хост в IP.
        """
        # Проверяем кэш
        cached_ip = self._get_from_cache(host)
        if cached_ip:
            return DNSResult(host=host, ip=cached_ip, success=True, cached=True)

        async with self.semaphore:
            try:
                if self.resolver and AIODNS_AVAILABLE:
                    # Async через aiodns
                    result = await self.resolver.gethostbyname(host, socket.AF_INET)
                    ip = result.addresses[0] if result.addresses else None
                else:
                    # Fallback на синхронный socket (в executor)
                    loop = asyncio.get_event_loop()
                    ip = await loop.run_in_executor(None, socket.gethostbyname, host)

                if ip:
                    self._put_to_cache(host, ip)
                    return DNSResult(host=host, ip=ip, success=True, cached=False)
                else:
                    return DNSResult(host=host, success=False, error="No addresses")

            except asyncio.TimeoutError:
                return DNSResult(host=host, success=False, error="Timeout")
            except (aiodns.error.DNSError, socket.gaierror) as exc:
                return DNSResult(host=host, success=False, error=f"DNS error: {exc}")
            except Exception as exc:
                return DNSResult(host=host, success=False, error=f"Unexpected: {exc}")

    async def resolve_batch(self, hosts: List[str]) -> List[DNSResult]:
        """
        Резолвит список хостов параллельно.
        """
        tasks = [self.resolve_one(host) for host in hosts]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results

    def resolve_batch_sync(self, hosts: List[str]) -> List[DNSResult]:
        """
        Синхронная обёртка для resolve_batch.
        """
        return asyncio.run(self.resolve_batch(hosts))

    def clear_cache(self) -> None:
        """Очистить кэш."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Статистика кэша."""
        now = time.time()
        valid = sum(1 for _, ts in self._cache.values() if now - ts < self.cache_ttl)
        return {
            "total": len(self._cache),
            "valid": valid,
            "expired": len(self._cache) - valid,
        }


# ── Удобные функции ───────────────────────────────────────────────


async def resolve_hosts_async(
    hosts: List[str],
    timeout: float = 2.0,
    max_concurrent: int = 50,
) -> List[DNSResult]:
    """
    Резолвит список хостов асинхронно.
    """
    resolver = AsyncDNSResolver(timeout=timeout, max_concurrent=max_concurrent)
    return await resolver.resolve_batch(hosts)


def resolve_hosts_sync(
    hosts: List[str],
    timeout: float = 2.0,
    max_concurrent: int = 50,
) -> List[DNSResult]:
    """
    Резолвит список хостов синхронно (блокирующий вызов).
    """
    resolver = AsyncDNSResolver(timeout=timeout, max_concurrent=max_concurrent)
    return resolver.resolve_batch_sync(hosts)
