from webapp import subscription


def test_gating_disabled_when_no_channel_configured(monkeypatch):
    monkeypatch.setattr(subscription, "REQUIRED_CHANNEL", "")
    assert subscription.gating_enabled() is False
    assert subscription.is_subscribed(user_id=1) is True


def test_subscribed_status_grants_access(monkeypatch, tmp_path):
    monkeypatch.setattr(subscription, "REQUIRED_CHANNEL", "@some_channel")
    monkeypatch.setattr("bot.storage.DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(subscription, "_check_via_api", lambda user_id: True)

    assert subscription.is_subscribed(user_id=42) is True


def test_left_status_denies_access(monkeypatch, tmp_path):
    monkeypatch.setattr(subscription, "REQUIRED_CHANNEL", "@some_channel")
    monkeypatch.setattr("bot.storage.DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(subscription, "_check_via_api", lambda user_id: False)

    assert subscription.is_subscribed(user_id=42) is False


def test_failed_api_check_fails_closed(monkeypatch, tmp_path):
    # get_chat_member_status возвращает None при сбое запроса -> _check_via_api должен дать False
    monkeypatch.setattr(subscription, "REQUIRED_CHANNEL", "@some_channel")
    monkeypatch.setattr("bot.storage.DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(subscription, "get_chat_member_status", lambda chat_id, user_id: None)

    assert subscription._check_via_api(user_id=42) is False


def test_result_is_cached_and_not_rechecked_within_ttl(monkeypatch, tmp_path):
    monkeypatch.setattr(subscription, "REQUIRED_CHANNEL", "@some_channel")
    monkeypatch.setattr("bot.storage.DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(subscription, "SUBSCRIPTION_CACHE_SECONDS", 999)

    calls = {"count": 0}

    def fake_check(user_id):
        calls["count"] += 1
        return True

    monkeypatch.setattr(subscription, "_check_via_api", fake_check)

    assert subscription.is_subscribed(user_id=42) is True
    assert subscription.is_subscribed(user_id=42) is True
    assert calls["count"] == 1  # второй вызов взят из кэша, а не из API


def test_force_refresh_bypasses_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(subscription, "REQUIRED_CHANNEL", "@some_channel")
    monkeypatch.setattr("bot.storage.DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(subscription, "SUBSCRIPTION_CACHE_SECONDS", 999)

    calls = {"count": 0}

    def fake_check(user_id):
        calls["count"] += 1
        return True

    monkeypatch.setattr(subscription, "_check_via_api", fake_check)

    subscription.is_subscribed(user_id=42)
    subscription.is_subscribed(user_id=42, force_refresh=True)
    assert calls["count"] == 2


def test_channel_info_builds_url_from_username(monkeypatch):
    monkeypatch.setattr(subscription, "REQUIRED_CHANNEL", "@romanvipsellers")
    monkeypatch.setattr(subscription, "CHANNEL_URL", "")
    info = subscription.channel_info()
    assert info["channel_url"] == "https://t.me/romanvipsellers"
