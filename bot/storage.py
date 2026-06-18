"""
Простое хранилище на SQLite.

Для прототипа этого достаточно. Перед реальным продакшен-использованием
рекомендуется:
  1. Шифровать поле wb_token (например, через cryptography.fernet),
     ключ шифрования держать отдельно от базы (переменная окружения).
  2. Не логировать токен ни при каких обстоятельствах.
  3. Дать пользователю команду /forget для немедленного удаления токена.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from bot.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    wb_token TEXT
);

CREATE TABLE IF NOT EXISTS cost_prices (
    telegram_id INTEGER,
    nm_id TEXT,
    cost_price REAL,
    PRIMARY KEY (telegram_id, nm_id)
);

CREATE TABLE IF NOT EXISTS ad_spend (
    telegram_id INTEGER,
    nm_id TEXT,
    period TEXT,
    spend REAL,
    PRIMARY KEY (telegram_id, nm_id, period)
);

CREATE TABLE IF NOT EXISTS subscription_cache (
    telegram_id INTEGER PRIMARY KEY,
    is_subscribed INTEGER,
    checked_at INTEGER
);
"""


def _ensure_dir() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_token(telegram_id: int, token: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (telegram_id, wb_token) VALUES (?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET wb_token = excluded.wb_token",
            (telegram_id, token),
        )


def get_token(telegram_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT wb_token FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row[0] if row else None


def forget_token(telegram_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))


def set_cost_price(telegram_id: int, nm_id: str, cost_price: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cost_prices (telegram_id, nm_id, cost_price) VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id, nm_id) DO UPDATE SET cost_price = excluded.cost_price",
            (telegram_id, nm_id, cost_price),
        )


def get_cost_prices(telegram_id: int) -> dict[str, float]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT nm_id, cost_price FROM cost_prices WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchall()
        return {nm_id: price for nm_id, price in rows}


def set_ad_spend(telegram_id: int, nm_id: str, period: str, spend: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ad_spend (telegram_id, nm_id, period, spend) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(telegram_id, nm_id, period) DO UPDATE SET spend = excluded.spend",
            (telegram_id, nm_id, period, spend),
        )


def get_ad_spend(telegram_id: int, period: str) -> dict[str, float]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT nm_id, spend FROM ad_spend WHERE telegram_id = ? AND period = ?",
            (telegram_id, period),
        ).fetchall()
        return {nm_id: spend for nm_id, spend in rows}


def get_subscription_cache(telegram_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT is_subscribed, checked_at FROM subscription_cache WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if not row:
            return None
        return {"is_subscribed": bool(row[0]), "checked_at": row[1]}


def set_subscription_cache(telegram_id: int, is_subscribed: bool, checked_at: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO subscription_cache (telegram_id, is_subscribed, checked_at) VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET is_subscribed = excluded.is_subscribed, "
            "checked_at = excluded.checked_at",
            (telegram_id, int(is_subscribed), checked_at),
        )
