"""Smoke tests against the real database (requires pipeline + predictions run)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta():
    r = client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["players_in_pool"] > 300
    assert body["next_gameweek"] is not None


def test_teams():
    r = client.get("/api/teams")
    assert r.status_code == 200
    assert len(r.json()) == 20


def test_players_list_sorted_and_filtered():
    r = client.get("/api/players", params={"position": 4, "limit": 10})
    assert r.status_code == 200
    rows = r.json()
    assert 0 < len(rows) <= 10
    assert all(p["position"] == 4 for p in rows)
    preds = [p["predicted_points"] for p in rows if p["predicted_points"] is not None]
    assert preds == sorted(preds, reverse=True)


def test_players_search():
    r = client.get("/api/players", params={"search": "haaland"})
    assert r.status_code == 200
    assert any(p["web_name"] == "Haaland" for p in r.json())


def test_player_detail():
    code = client.get("/api/players", params={"search": "haaland"}).json()[0]["code"]
    r = client.get(f"/api/players/{code}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["history"]) > 50
    assert len(body["upcoming"]) > 0
    assert len(body["predictions"]) > 0


def test_player_detail_404():
    assert client.get("/api/players/999999999").status_code == 404


def test_predictions():
    r = client.get("/api/predictions", params={"limit": 20})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 20
    assert rows[0]["predicted_points"] >= rows[-1]["predicted_points"]


@pytest.mark.parametrize("budget,horizon", [(100.0, 1), (85.0, 3), (100.0, 5)])
def test_optimal_team(budget, horizon):
    r = client.get("/api/optimal-team", params={"budget": budget, "horizon": horizon})
    assert r.status_code == 200
    body = r.json()
    assert not body["infeasible"]
    # Short of the ask only if predictions don't reach that far.
    assert 0 < len(body["weeks"]) <= horizon
    assert len(body["weeks"]) == body["horizon"]
    assert [w["gameweek"] for w in body["weeks"]] == body["gameweeks"]
    assert body["total_expected_points"] == pytest.approx(
        sum(w["expected_points"] for w in body["weeks"]), abs=0.01
    )

    for i, week in enumerate(body["weeks"]):
        assert len(week["starting_xi"]) == 11
        assert len(week["bench"]) == 4
        assert week["total_cost"] <= budget
        assert sum(1 for p in week["starting_xi"] if p["is_captain"]) == 1
        positions = [p["position"] for p in week["starting_xi"]]
        assert positions.count(1) == 1
        assert positions.count(2) >= 3

        assert len(week["transfers_in"]) == len(week["transfers_out"])
        if i == 0:
            # The opening squad is a free pick, so nothing is transferred yet.
            assert week["bank_before"] is None and week["transfers_used"] == 0
        else:
            assert week["transfers_used"] <= week["bank_before"]
            assert week["bank_after"] == week["bank_before"] - week["transfers_used"]
