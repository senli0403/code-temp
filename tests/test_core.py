import os
import tempfile
from datetime import date, datetime, timezone

os.environ["NQ_KLINE_HOME"] = tempfile.mkdtemp()

import pandas as pd
from fastapi.testclient import TestClient

from nqkline import ai, data
from nqkline.indicators import add_sma
from nqkline.server import app


def _df():
    idx = pd.date_range("2025-01-06 00:00", periods=120, freq="1min", tz="UTC")
    close = pd.Series(range(120), index=idx, dtype=float)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close + 0.5, "volume": 10.0})


def test_aggregate_5m():
    out = data.aggregate(_df(), 5)
    assert len(out) == 24
    first = out.iloc[0]
    assert first.open == 0 and first.close == 4.5 and first.high == 5 and first.low == -1 and first.volume == 50


def test_sma():
    out = add_sma(data.aggregate(_df(), 5))
    assert pd.isna(out.ma10.iloc[8]) and not pd.isna(out.ma10.iloc[9])
    assert out.ma10.iloc[9] == out.close.iloc[:10].mean()


def test_candle_color_taiwan():
    assert data.candle_color(1, 2) == "紅" and data.candle_color(2, 1) == "綠" and data.candle_color(1, 1) == "平"


def test_local_epoch_shift():
    idx = pd.DatetimeIndex(["2025-01-06 00:00"], tz="UTC")
    assert data.to_local_epoch(idx, "Asia/Taipei")[0] - data.to_local_epoch(idx, "UTC")[0] == 8 * 3600


def test_bars_table_has_colors():
    bars = add_sma(data.aggregate(_df(), 5))
    txt = ai.bars_table(bars, "UTC", 5)
    assert "K色" in txt and "紅" in txt


def test_api_demo_flow():
    c = TestClient(app)
    r = c.post("/api/load", json={"start": "2025-01-07", "end": "2025-01-09", "interval": "5", "demo": True})
    assert r.status_code == 200
    j = r.json()
    assert j["count"] > 100 and set(j["ma"]) == {"10", "60", "72", "100"}
    assert j["ma"]["100"], "warm-up should fill MA100 within the visible range"
    r15 = c.post("/api/bars", json={"interval": "15"}).json()
    assert r15["count"] * 3 == j["count"] or abs(r15["count"] * 3 - j["count"]) < 6
    assert c.post("/api/bars", json={"interval": "7"}).status_code == 400


def test_chat_without_key_errors_cleanly():
    c = TestClient(app)
    c.post("/api/load", json={"start": "2025-01-07", "end": "2025-01-08", "interval": "5", "demo": True})
    r = c.post("/api/chat", json={"message": "hi", "interval": "5"})
    assert r.status_code == 400 and "API Key" in r.json()["detail"]


def test_notes_roundtrip():
    n = ai.add_note("t", "c")
    assert any(x["id"] == n["id"] for x in ai.list_notes())
    ai.delete_note(n["id"])
    assert not ai.list_notes()
