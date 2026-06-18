from bot.diagnostics import diagnose_card, diagnose_cards_from_nm_report


def test_low_views_flags_visibility_problem():
    d = diagnose_card("999", views=40, add_to_cart=9, orders=7)
    assert "видимост" in d.summary().lower()


def test_low_view_to_cart_flags_card_content_problem():
    # 1800 показов, 60 в корзину = 3.3% -> ниже ориентира 6%
    d = diagnose_card("333333", views=1800, add_to_cart=60, orders=28)
    assert d.view_to_cart < 0.06
    assert "фото" in d.summary().lower() or "цен" in d.summary().lower()


def test_good_funnel_has_no_negative_verdict_keywords():
    # 5200 показов, 980 в корзину (18.8%), 247 заказов из 980 (25.2%)
    d = diagnose_card("222222", views=5200, add_to_cart=980, orders=247)
    assert d.view_to_cart > 0.12
    assert "хорошая" in d.summary().lower()


def test_high_drr_flags_ad_warning():
    d = diagnose_card("111111", views=3100, add_to_cart=410, orders=167, drr_pct=30.0)
    assert "минус" in d.summary().lower()


def test_diagnose_cards_from_nm_report_parses_demo_shape():
    cards = [
        {
            "nmID": 111111,
            "statistics": {"selectedPeriod": {"openCardCount": 3100, "addToCartCount": 410, "ordersCount": 167}},
        }
    ]
    diags = diagnose_cards_from_nm_report(cards)
    assert len(diags) == 1
    assert diags[0].nm_id == "111111"
    assert diags[0].views == 3100
