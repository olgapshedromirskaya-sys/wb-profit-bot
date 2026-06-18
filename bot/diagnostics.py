"""
Диагностика карточки товара: превращает сырые цифры воронки
(показы/переходы → корзина → заказ) в конкретный текстовый вывод —
что именно похоже на проблему и в какую сторону копать.

Это умышленно простые пороговые правила (см. BENCHMARKS в config.py),
а не ML — задача прототипа дать продавцу понятную первую подсказку,
а не точную диагностику. Пороги легко поправить под свою категорию.
"""
from __future__ import annotations

from dataclasses import dataclass

from bot.config import BENCHMARKS


@dataclass
class CardDiagnosis:
    nm_id: str
    views: int
    add_to_cart: int
    orders: int
    view_to_cart: float
    cart_to_order: float
    drr_pct: float | None
    verdicts: list[str]

    def summary(self) -> str:
        if not self.verdicts:
            return "Воронка в норме, явных проблем не видно."
        return " ".join(self.verdicts)


def diagnose_card(
    nm_id: str,
    views: int,
    add_to_cart: int,
    orders: int,
    drr_pct: float | None = None,
) -> CardDiagnosis:
    view_to_cart = (add_to_cart / views) if views else 0.0
    cart_to_order = (orders / add_to_cart) if add_to_cart else 0.0

    verdicts: list[str] = []

    if views < 50:
        verdicts.append(
            "Очень мало показов/переходов — вероятно, проблема не в карточке, "
            "а в видимости: проверьте ставки в рекламе и SEO-описание под ключевые запросы."
        )
    elif view_to_cart < BENCHMARKS["view_to_cart_min"]:
        verdicts.append(
            f"Низкая конверсия в корзину ({view_to_cart:.1%} при ориентире "
            f"{BENCHMARKS['view_to_cart_min']:.0%}+) — похоже на проблему с главным фото, "
            "ценой относительно конкурентов или заголовком."
        )
    elif view_to_cart >= BENCHMARKS["view_to_cart_good"]:
        verdicts.append(f"Конверсия в корзину хорошая ({view_to_cart:.1%}) — карточка цепляет.")

    if add_to_cart >= 10 and cart_to_order < BENCHMARKS["cart_to_order_min"]:
        verdicts.append(
            f"Добавляют в корзину, но редко заказывают ({cart_to_order:.1%} при ориентире "
            f"{BENCHMARKS['cart_to_order_min']:.0%}+) — вероятно дело в описании/отзывах/сроках "
            "доставки или в финальной цене с учётом скидок."
        )
    elif add_to_cart >= 10 and cart_to_order >= BENCHMARKS["cart_to_order_good"]:
        verdicts.append(f"Из корзины в заказ конвертит хорошо ({cart_to_order:.1%}).")

    if drr_pct is not None:
        if drr_pct >= BENCHMARKS["drr_critical"] * 100:
            verdicts.append(
                f"ДРР {drr_pct:.1f}% — реклама, скорее всего, работает в минус, "
                "стоит снизить ставку или приостановить кампанию."
            )
        elif drr_pct >= BENCHMARKS["drr_warning"] * 100:
            verdicts.append(f"ДРР {drr_pct:.1f}% выше комфортного уровня — присмотритесь к ставке.")

    return CardDiagnosis(
        nm_id=nm_id,
        views=views,
        add_to_cart=add_to_cart,
        orders=orders,
        view_to_cart=view_to_cart,
        cart_to_order=cart_to_order,
        drr_pct=drr_pct,
        verdicts=verdicts,
    )


def diagnose_cards_from_nm_report(cards: list[dict], drr_by_nm: dict[str, float] | None = None) -> list[CardDiagnosis]:
    """
    cards — список карточек из fetch_nm_report_detail (или тестовых данных),
    ожидаются поля nmID, statistics.selectedPeriod.openCardCount,
    .addToCartCount, .ordersCount (имена точно сверьте с актуальным
    ответом API — у WB они периодически меняют вложенность).
    """
    drr_by_nm = drr_by_nm or {}
    result = []
    for card in cards:
        nm_id = str(card.get("nmID", card.get("nm_id", "unknown")))
        period = card.get("statistics", {}).get("selectedPeriod", card)
        views = period.get("openCardCount", 0) or 0
        add_to_cart = period.get("addToCartCount", 0) or 0
        orders = period.get("ordersCount", 0) or 0
        result.append(diagnose_card(nm_id, views, add_to_cart, orders, drr_by_nm.get(nm_id)))
    return result
