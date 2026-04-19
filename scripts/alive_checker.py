"""
Alive Checker — async TCP ping для проверки доступности VPN-нод.

Особенности:
- Async TCP connect для параллельной проверки
- Batch processing
- Измерение latency (ping)
- Статистика по результатам
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import List, Optional, Dict

from .parser import VPNNode
from .constants import DEFAULT_PING_TIMEOUT


@dataclass
class AliveResult:
    """Результат проверки одной ноды."""
    host: str
    port: int
    alive: bool
    ping_ms: Optional[int] = None
    error: Optional[str] = None


class AliveChecker:
    """
    Async TCP ping checker для VPN-нод.

    Проверяет доступность через TCP connect и измеряет latency.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_PING_TIMEOUT,
        max_concurrent: int = 100,
        batch_size: int = 200,
    ):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.batch_size = batch_size
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def check_one(self, host: str, port: int) -> AliveResult:
        """
        Проверяет одну ноду через TCP connect.
        """
        async with self.semaphore:
            start_time = time.monotonic()

            try:
                # Пытаемся установить TCP соединение
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=self.timeout
                )

                # Закрываем соединение
                writer.close()
                await writer.wait_closed()

                # Вычисляем ping
                duration = time.monotonic() - start_time
                ping_ms = int(duration * 1000)

                return AliveResult(
                    host=host,
                    port=port,
                    alive=True,
                    ping_ms=ping_ms,
                )

            except asyncio.TimeoutError:
                return AliveResult(
                    host=host,
                    port=port,
                    alive=False,
                    error="Timeout",
                )
            except (OSError, ConnectionError) as exc:
                return AliveResult(
                    host=host,
                    port=port,
                    alive=False,
                    error=f"Connection error: {type(exc).__name__}",
                )
            except Exception as exc:
                return AliveResult(
                    host=host,
                    port=port,
                    alive=False,
                    error=f"Unexpected: {exc}",
                )

    async def check_batch(self, nodes: List[VPNNode]) -> List[AliveResult]:
        """
        Проверяет батч нод параллельно.
        """
        tasks = [
            self.check_one(node.host, node.port)
            for node in nodes
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results

    def check_batch_sync(self, nodes: List[VPNNode]) -> List[AliveResult]:
        """
        Синхронная обёртка для check_batch.
        """
        return asyncio.run(self.check_batch(nodes))

    def check_all(self, nodes: List[VPNNode], verbose: bool = False) -> None:
        """
        Проверяет все ноды и обновляет их extra поля.

        Добавляет в node.extra:
        - alive: bool
        - ping: int (ms) или None
        """
        total = len(nodes)
        checked = 0

        for i in range(0, total, self.batch_size):
            batch = nodes[i:i + self.batch_size]
            results = self.check_batch_sync(batch)

            # Применяем результаты
            for node, result in zip(batch, results):
                node.extra["alive"] = result.alive
                node.extra["ping"] = result.ping_ms

            checked += len(batch)

            if verbose:
                alive_count = sum(1 for r in results if r.alive)
                print(
                    f"      [Alive] {checked}/{total} checked, "
                    f"{alive_count}/{len(results)} alive in batch",
                    flush=True
                )

    def get_stats(self, nodes: List[VPNNode]) -> Dict[str, any]:
        """
        Статистика по результатам проверки.
        """
        total = len(nodes)
        alive = sum(1 for n in nodes if n.extra.get("alive", False))
        dead = total - alive

        pings = [n.extra.get("ping") for n in nodes if n.extra.get("ping")]
        avg_ping = int(sum(pings) / len(pings)) if pings else None
        min_ping = min(pings) if pings else None
        max_ping = max(pings) if pings else None

        return {
            "total": total,
            "alive": alive,
            "dead": dead,
            "alive_ratio": round(alive / total, 4) if total > 0 else 0.0,
            "avg_ping_ms": avg_ping,
            "min_ping_ms": min_ping,
            "max_ping_ms": max_ping,
        }


# ── Удобные функции ───────────────────────────────────────────────


def check_alive(
    nodes: List[VPNNode],
    timeout: float = DEFAULT_PING_TIMEOUT,
    max_concurrent: int = 100,
    verbose: bool = False,
) -> Dict[str, any]:
    """
    Проверяет доступность нод и возвращает статистику.

    Args:
        nodes: список VPNNode
        timeout: таймаут на одну проверку (секунды)
        max_concurrent: максимум параллельных проверок
        verbose: выводить прогресс

    Returns:
        статистика: {total, alive, dead, alive_ratio, avg_ping_ms, ...}
    """
    checker = AliveChecker(
        timeout=timeout,
        max_concurrent=max_concurrent,
    )
    checker.check_all(nodes, verbose=verbose)
    return checker.get_stats(nodes)


async def check_alive_async(
    nodes: List[VPNNode],
    timeout: float = DEFAULT_PING_TIMEOUT,
    max_concurrent: int = 100,
) -> List[AliveResult]:
    """
    Асинхронная проверка нод.
    """
    checker = AliveChecker(
        timeout=timeout,
        max_concurrent=max_concurrent,
    )
    return await checker.check_batch(nodes)
