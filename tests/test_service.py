from webapp.service import demo_dashboard


def test_demo_dashboard_has_total_and_skus():
    data = demo_dashboard()
    assert "total" in data
    assert "skus" in data
    assert len(data["skus"]) == 4
    assert data["connected"] is True
    assert data["demo"] is True


def test_demo_dashboard_skus_sorted_worst_first():
    data = demo_dashboard()
    profits = [s["net_profit"] for s in data["skus"]]
    assert profits == sorted(profits)


def test_demo_dashboard_merges_profit_and_diagnosis():
    data = demo_dashboard()
    by_id = {s["nm_id"]: s for s in data["skus"]}
    # 444444 в демо-данных имеет всего 40 показов -> диагностика про видимость
    assert "видимост" in by_id["444444"]["diagnosis"].lower()
    # у 444444 не задана себестоимость -> has_cost_price должен быть False
    assert by_id["444444"]["has_cost_price"] is False
    # у 111111 задана себестоимость 300 в demo_dashboard -> has_cost_price True
    assert by_id["111111"]["has_cost_price"] is True


def test_demo_dashboard_total_matches_sum_of_skus():
    data = demo_dashboard()
    total_profit = data["total"]["net_profit"]
    sum_profit = sum(s["net_profit"] for s in data["skus"])
    assert round(total_profit, 2) == round(sum_profit, 2)
