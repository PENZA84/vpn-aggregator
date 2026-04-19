"""
History DB — SQLite для хранения истории метрик источников и нод.

Таблицы:
- sources: информация об источниках
- source_metrics: метрики источников по времени
- nodes: уникальные ноды
- node_checks: результаты проверок нод
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from .parser import VPNNode


class HistoryDB:
    """
    SQLite база для хранения истории метрик.

    Позволяет:
    - Отслеживать изменения метрик источников во времени
    - Хранить историю проверок нод (alive, ping)
    - Анализировать деградацию качества
    - Строить графики метрик
    """

    def __init__(self, db_path: str = "data/history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Инициализирует базу данных и создаёт таблицы."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

        cursor = self.conn.cursor()

        # Таблица источников
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                source_url TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица метрик источников
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS source_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_nodes INTEGER,
                unique_ips INTEGER,
                eu_share REAL,
                bad_country_share REAL,
                avg_ping INTEGER,
                alive_ratio REAL,
                score REAL,
                FOREIGN KEY (source_id) REFERENCES sources(source_id)
            )
        """)

        # Таблица нод
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                protocol TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                uuid TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица проверок нод
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS node_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                alive BOOLEAN,
                ping_ms INTEGER,
                country TEXT,
                asn INTEGER,
                FOREIGN KEY (node_id) REFERENCES nodes(node_id)
            )
        """)

        # Индексы для быстрого поиска
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_metrics_timestamp
            ON source_metrics(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_node_checks_timestamp
            ON node_checks(timestamp)
        """)

        self.conn.commit()

    def _node_to_id(self, node: VPNNode) -> str:
        """Генерирует уникальный ID для ноды."""
        return f"{node.protocol}_{node.host}_{node.port}_{node.uuid or node.password or ''}"

    def save_source_metrics(
        self,
        source_id: str,
        source_name: str,
        metrics: Dict,
        source_url: Optional[str] = None,
    ) -> None:
        """
        Сохраняет метрики источника.
        """
        cursor = self.conn.cursor()

        # Обновляем/создаём запись источника
        cursor.execute("""
            INSERT INTO sources (source_id, source_name, source_url, last_seen)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source_id) DO UPDATE SET
                last_seen = CURRENT_TIMESTAMP,
                source_url = COALESCE(excluded.source_url, source_url)
        """, (source_id, source_name, source_url))

        # Сохраняем метрики
        cursor.execute("""
            INSERT INTO source_metrics (
                source_id, total_nodes, unique_ips, eu_share,
                bad_country_share, avg_ping, alive_ratio, score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source_id,
            metrics.get("total_nodes"),
            metrics.get("unique_ips"),
            metrics.get("eu_share"),
            metrics.get("bad_country_share"),
            metrics.get("avg_ping"),
            metrics.get("alive_ratio"),
            metrics.get("score"),
        ))

        self.conn.commit()

    def save_node_check(self, node: VPNNode) -> None:
        """
        Сохраняет результат проверки ноды.
        """
        cursor = self.conn.cursor()
        node_id = self._node_to_id(node)
        extra = node.extra or {}

        # Обновляем/создаём запись ноды
        cursor.execute("""
            INSERT INTO nodes (node_id, protocol, host, port, uuid, last_seen)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(node_id) DO UPDATE SET
                last_seen = CURRENT_TIMESTAMP
        """, (node_id, node.protocol, node.host, node.port, node.uuid))

        # Сохраняем результат проверки
        cursor.execute("""
            INSERT INTO node_checks (node_id, alive, ping_ms, country, asn)
            VALUES (?, ?, ?, ?, ?)
        """, (
            node_id,
            extra.get("alive"),
            extra.get("ping"),
            extra.get("country"),
            extra.get("asn"),
        ))

        self.conn.commit()

    def save_nodes_batch(self, nodes: List[VPNNode]) -> None:
        """
        Сохраняет батч нод.
        """
        for node in nodes:
            self.save_node_check(node)

    def get_source_history(
        self,
        source_id: str,
        days: int = 30,
    ) -> List[Dict]:
        """
        Возвращает историю метрик источника за последние N дней.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM source_metrics
            WHERE source_id = ?
            AND timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp DESC
        """, (source_id, days))

        return [dict(row) for row in cursor.fetchall()]

    def get_node_history(
        self,
        node_id: str,
        days: int = 30,
    ) -> List[Dict]:
        """
        Возвращает историю проверок ноды за последние N дней.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM node_checks
            WHERE node_id = ?
            AND timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp DESC
        """, (node_id, days))

        return [dict(row) for row in cursor.fetchall()]

    def get_degraded_sources(
        self,
        threshold: float = 0.2,
        days: int = 7,
    ) -> List[Tuple[str, float, float]]:
        """
        Находит источники с деградацией качества.

        Returns:
            [(source_id, old_score, new_score), ...]
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            WITH recent AS (
                SELECT source_id, AVG(score) as avg_score
                FROM source_metrics
                WHERE timestamp >= datetime('now', '-' || ? || ' days')
                GROUP BY source_id
            ),
            old AS (
                SELECT source_id, AVG(score) as avg_score
                FROM source_metrics
                WHERE timestamp < datetime('now', '-' || ? || ' days')
                AND timestamp >= datetime('now', '-' || ? || ' days')
                GROUP BY source_id
            )
            SELECT
                recent.source_id,
                old.avg_score as old_score,
                recent.avg_score as new_score
            FROM recent
            JOIN old ON recent.source_id = old.source_id
            WHERE (old.avg_score - recent.avg_score) > ?
            ORDER BY (old.avg_score - recent.avg_score) DESC
        """, (days, days, days * 2, threshold))

        return cursor.fetchall()

    def get_stats(self) -> Dict:
        """
        Общая статистика базы.
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM sources")
        total_sources = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM nodes")
        total_nodes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM source_metrics")
        total_metrics = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM node_checks")
        total_checks = cursor.fetchone()[0]

        return {
            "total_sources": total_sources,
            "total_nodes": total_nodes,
            "total_metrics": total_metrics,
            "total_checks": total_checks,
        }

    def close(self) -> None:
        """Закрывает соединение с базой."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
