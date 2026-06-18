"""
Гейт доступа: "нет подписки на канал — нет данных".

Намеренно отделено от webapp/auth.py: auth.py отвечает на вопрос
"кто это" (подлинность initData), subscription.py отвечает на вопрос
"имеет ли право" (подписан ли он на канал прямо сейчас). Это разные
проверки, и со временем гейтов может стать больше (например, активная
платная подписка) — они не должны мешать друг другу.

ВАЖНО (fail-closed): если проверить статус не удалось (бот не админ
канала, Telegram недоступен, неверный chat_id) — доступ ЗАКРЫВАЕТСЯ,
а не открывается. Для лид-магнита, который должен заставлять держать
подписку, открывать доступ "на всякий случай" при сбое — ошибка.
Если это нежелательно для вашего случая, поменяйте поведение в
is_subscribed() ниже осознанно, а не как побочный эффект.
"""
from __future__ import annotations

import time

from bot import storage
from bot.config import CHANNEL_URL, REQUIRED_CHANNEL, SUBSCRIPTION_CACHE_SECONDS
from bot.telegram_api import SUBSCRIBED_STATUSES, get_chat_member_status


def gating_enabled() -> bool:
    return bool(REQUIRED_CHANNEL)


def channel_info() -> dict:
    url = CHANNEL_URL or (
        f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}" if REQUIRED_CHANNEL.startswith("@") else ""
    )
    return {"channel": REQUIRED_CHANNEL, "channel_url": url}


def _check_via_api(user_id: int) -> bool:
    status = get_chat_member_status(REQUIRED_CHANNEL, user_id)
    if status is None:
        return False  # fail-closed, см. докстринг модуля
    return status in SUBSCRIBED_STATUSES


def is_subscribed(user_id: int, force_refresh: bool = False) -> bool:
    """
    True, если подписка не требуется (REQUIRED_CHANNEL не задан) или
    подтверждена через Bot API (с кэшем на SUBSCRIPTION_CACHE_SECONDS).
    """
    if not gating_enabled():
        return True

    if not force_refresh:
        cached = storage.get_subscription_cache(user_id)
        if cached and (time.time() - cached["checked_at"] < SUBSCRIPTION_CACHE_SECONDS):
            return cached["is_subscribed"]

    fresh = _check_via_api(user_id)
    storage.set_subscription_cache(user_id, fresh, int(time.time()))
    return fresh
