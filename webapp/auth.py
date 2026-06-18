"""
Проверка подлинности данных, которые Telegram передаёт Mini App
(initData), по официальному алгоритму:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Без этой проверки любой человек мог бы прислать произвольный user_id
в заголовке и читать/писать чужие данные. С проверкой — подделать
data_check_string невозможно без знания токена бота.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from dataclasses import dataclass


@dataclass
class TelegramUser:
    user_id: int
    first_name: str
    username: str | None
    auth_date: int


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> TelegramUser | None:
    if not init_data or not bot_token:
        return None

    try:
        pairs = urllib.parse.parse_qsl(init_data, strict_parsing=True)
    except ValueError:
        return None

    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    auth_date = int(data.get("auth_date", 0))
    if max_age_seconds and time.time() - auth_date > max_age_seconds:
        return None

    user_raw = data.get("user")
    if not user_raw:
        return None
    user = json.loads(user_raw)

    return TelegramUser(
        user_id=user["id"],
        first_name=user.get("first_name", ""),
        username=user.get("username"),
        auth_date=auth_date,
    )
