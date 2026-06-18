"""
Тонкий клиент к Telegram Bot API (api.telegram.org) — отдельно от
bot/wb_api.py, который ходит в API Wildberries. Разные платформы,
разная аутентификация, разные форматы ошибок — смешивать их в одном
модуле было бы запутанно.

Сейчас здесь только то, что нужно для проверки подписки на канал.
"""
from __future__ import annotations

import requests

from bot.config import BOT_TOKEN, TELEGRAM_API_BASE

REQUEST_TIMEOUT = 10

# Эти статусы означают "состоит в канале/чате". "left" и "kicked" — не состоит.
SUBSCRIBED_STATUSES = {"creator", "administrator", "member", "restricted"}


def get_chat_member_status(chat_id: str, user_id: int) -> str | None:
    """
    Возвращает статус участника ("member", "left", "kicked", ...)
    или None, если запрос не удался (бот не админ канала, неверный
    chat_id, сетевая ошибка и т.п.) — это сознательно отличается от
    статуса "left", чтобы вызывающий код мог решить, как обрабатывать
    сбой проверки отдельно от подтверждённой отписки.
    """
    if not chat_id or not BOT_TOKEN:
        return None
    url = f"{TELEGRAM_API_BASE}/bot{BOT_TOKEN}/getChatMember"
    try:
        resp = requests.get(
            url, params={"chat_id": chat_id, "user_id": user_id}, timeout=REQUEST_TIMEOUT
        )
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    if not data.get("ok"):
        # Частые причины: бот не добавлен в канал админом, неверный chat_id.
        return None

    return data.get("result", {}).get("status")
