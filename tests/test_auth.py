import hashlib
import hmac
import json
import time
import urllib.parse

from webapp.auth import validate_init_data

BOT_TOKEN = "123456:test-token"


def _build_init_data(user_id: int = 42, auth_date: int | None = None, tamper: bool = False) -> str:
    auth_date = auth_date if auth_date is not None else int(time.time())
    user = {"id": user_id, "first_name": "Иван", "username": "ivan_seller"}
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAEEgg",
        "user": json.dumps(user, ensure_ascii=False),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if tamper:
        digest = "0" * len(digest)
    fields["hash"] = digest
    return urllib.parse.urlencode(fields)


def test_valid_init_data_is_accepted():
    init_data = _build_init_data(user_id=777)
    user = validate_init_data(init_data, BOT_TOKEN)
    assert user is not None
    assert user.user_id == 777
    assert user.username == "ivan_seller"


def test_tampered_hash_is_rejected():
    init_data = _build_init_data(tamper=True)
    assert validate_init_data(init_data, BOT_TOKEN) is None


def test_wrong_bot_token_is_rejected():
    init_data = _build_init_data()
    assert validate_init_data(init_data, "different-token") is None


def test_expired_auth_date_is_rejected():
    old_auth_date = int(time.time()) - 999999
    init_data = _build_init_data(auth_date=old_auth_date)
    assert validate_init_data(init_data, BOT_TOKEN, max_age_seconds=86400) is None


def test_empty_init_data_is_rejected():
    assert validate_init_data("", BOT_TOKEN) is None
