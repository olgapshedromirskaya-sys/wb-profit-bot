"""
Конфигурация проекта.

Все «магические» URL и константы собраны здесь, чтобы при изменении
эндпоинтов Wildberries (а они меняются) не искать их по всему коду.

ВАЖНО: перед продакшен-использованием сверьте пути и названия полей
с актуальной документацией https://dev.wildberries.ru/ — API маркетплейсов
меняется чаще, чем хотелось бы.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class WBEndpoints:
    # Детальный отчёт о реализации (комиссии, логистика, хранение, выплаты).
    # Самый стабильный и самый информативный отчёт для расчёта реальной прибыли.
    realization_report: str = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"

    # Воронка по карточке: показы/переходы в карточку, добавления в корзину, заказы.
    nm_report_detail: str = "https://seller-analytics-api.wildberries.ru/api/v2/nm-report/detail"

    # Заказы и продажи (упрощённый поток, для быстрых сверок).
    orders: str = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
    sales: str = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"


WB = WBEndpoints()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "./data/users.db")
DEMO_ONLY = os.getenv("DEMO_ONLY", "false").lower() == "true"

# Публичный HTTPS-адрес мини-аппа (см. webapp/). Telegram требует HTTPS,
# поэтому для локальной разработки понадобится туннель (ngrok/cloudflared).
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com")

# --- Обязательная подписка на канал ---
# chat_id канала для проверки через Bot API: @username канала ИЛИ числовой
# id вида -1001234567890 (для приватных каналов). Бот ОБЯЗАН быть добавлен
# в этот канал администратором — иначе Telegram не отдаёт статус участника.
# Если оставить пустым — проверка подписки выключена (удобно для разработки).
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "")

# Публичная ссылка на канал, которую видит пользователь (кнопка "Подписаться").
# Может отличаться от REQUIRED_CHANNEL, если канал приватный с invite-ссылкой.
CHANNEL_URL = os.getenv("CHANNEL_URL", "")

# Сколько секунд доверяем кэшированному результату проверки подписки,
# не дёргая Bot API повторно на каждый запрос. Меньше — быстрее отреагирует
# на отписку, больше — меньше нагрузка на Telegram API и быстрее открывается
# дашборд. 1800 (30 минут) — разумный баланс для лид-магнита.
SUBSCRIPTION_CACHE_SECONDS = int(os.getenv("SUBSCRIPTION_CACHE_SECONDS", "1800"))

TELEGRAM_API_BASE = "https://api.telegram.org"

# Дефолтные ориентиры конверсии воронки для диагностики карточек.
# Это эмпирические "грубые" ориентиры по рынку WB, а не официальные данные
# Wildberries (внешние данные по нишам с 09.2025 ограничены) — подстройте
# под свою категорию, когда наберётся собственная статистика.
BENCHMARKS = {
    "view_to_cart_min": 0.06,   # доля посетителей карточки, добавивших в корзину
    "view_to_cart_good": 0.12,
    "cart_to_order_min": 0.25,  # доля добавивших в корзину, которые заказали
    "cart_to_order_good": 0.45,
    "drr_warning": 0.15,        # ДРР выше — повод насторожиться
    "drr_critical": 0.25,       # ДРР выше — реклама вероятно работает в минус
}
