"""
Минимальный набор хендлеров бота.

Вся продуктовая логика (прибыль, диагностика, токен, себестоимость)
теперь живёт в Mini App (см. webapp/). Бот нужен только чтобы:
  1. поприветствовать пользователя;
  2. дать кнопку, открывающую Mini App (Telegram WebApp).

Это сознательное архитектурное решение: бот — это просто "дверь",
весь интерфейс — веб-страница внутри Telegram, которую проще развивать,
тестировать в обычном браузере и которая выглядит как настоящий продукт,
а не набор команд.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot.config import WEBAPP_URL

router = Router()

WELCOME = (
    "Привет! Это бот, который показывает твою РЕАЛЬНУЮ прибыль на Wildberries "
    "(после комиссии, логистики, хранения, себестоимости и рекламы) и подсказывает, "
    "что не так с карточкой — по показам, корзинам и заказам.\n\n"
    "Жми кнопку ниже, чтобы открыть приложение."
)


def _webapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME, reply_markup=_webapp_keyboard())
