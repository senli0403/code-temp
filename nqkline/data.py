"""Databento download, local cache, resampling and payload building."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import config
from .indicators import MA_PERIODS, add_sma

INTERVALS = {"5": 5, "10": 10, "15": 15, "30": 30}
WARMUP_DAYS = 6  # extra history so MA100 is already filled on the first visible bar
OHLCV = ["open", "high", "low", "close", "volume"]


class DataError(Exception):
    pass


def utc_range(start: date, end: date, tz: str) -> tuple[datetime, datetime]:
    """Inclusive local dates -> [start, end) in UTC."""
    z = ZoneInfo(tz)
    s = datetime(start.year, start.month, start.day, tzinfo=z)
    e = datetime(end.year, end.month, end.day, tzinfo=z) + timedelta(days=1)
    return s.astimezone(timezone.utc), e.astimezone(timezone.utc)


def _client(cfg: dict):
    import databento as db

    if not cfg["databento_key"]:
        raise DataError("尚未設定 Databento API Key,請按右上角「設定」填入。")
    return db.Historical(cfg["databento_key"])


def _wrap(exc: Exception) -> DataError:
    msg = str(exc)
    if "data_end_after_available_end" in msg or "available" in msg.lower():
        msg += "\n(提示:查詢結束日可能超出 Databento 目前可取得的資料範圍,請把結束日提早一天試試。)"
    return DataError(f"Databento 錯誤:{msg}")


def estimate_cost(cfg: dict, start_utc: datetime, end_utc: datetime) -> dict:
    client = _client(cfg)
    kw = dict(dataset=cfg["dataset"], symbols=[cfg["symbol"]], schema="ohlcv-1m",
              stype_in="continuous", start=start_utc, end=end_utc)
    try:
        cost = client.metadata.get_cost(**kw)
        size = client.metadata.get_billable_size(**kw)
    except Exception as exc:  # databento raises several BentoError subclasses
        raise _wrap(exc) from exc
    return {"cost_usd": float(cost), "billable_bytes": int(size)}


def _cache_path(cfg: dict, start_utc: datetime, end_utc: datetime):
    raw = f"{cfg['dataset']}|{cfg['symbol']}|{start_utc.isoformat()}|{end_utc.isoformat()}"
    return config.CACHE_DIR / (hashlib.sha1(raw.encode()).hexdigest()[:16] + ".csv.gz")


def fetch_1m(cfg: dict, start_utc: datetime, end_utc: datetime) -> pd.DataFrame:
    """1-minute OHLCV from Databento (cached on disk so a repeat query costs nothing)."""
    config.ensure_dirs()
    path = _cache_path(cfg, start_utc, end_utc)
    if path.exists():
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
        return df
    client = _client(cfg)
    try:
        store = client.timeseries.get_range(
            dataset=cfg["dataset"], symbols=[cfg["symbol"]], stype_in="continuous",
            schema="ohlcv-1m", start=start_utc, end=end_utc)
        df = store.to_df()
    except Exception as exc:
        raise _wrap(exc) from exc
    if df.empty:
        raise DataError("這段日期沒有資料(可能是假日,或超出可查詢範圍)。")
    df = df[OHLCV].astype(float)
    df.index = pd.to_datetime(df.index, utc=True)
    df.sort_index().to_csv(path, compression="gzip")
    return df.sort_index()


def demo_1m(start_utc: datetime, end_utc: datetime) -> pd.DataFrame:
    """Synthetic random-walk data so the UI can be tried without any API key."""
    end_utc = min(end_utc, start_utc + timedelta(days=60))
    idx = pd.date_range(start_utc, end_utc, freq="1min", inclusive="left", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    rng = np.random.default_rng(int(start_utc.timestamp()) % 2**32)
    ret = rng.normal(0, 1.1, len(idx)) + 0.8 * np.sin(np.arange(len(idx)) / 600)
    close = 18000 + np.cumsum(ret)
    open_ = np.concatenate([[close[0]], close[:-1]])
    spread = np.abs(rng.normal(0, 1.5, len(idx)))
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    vol = rng.integers(50, 900, len(idx)).astype(float)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def aggregate(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes <= 1:
        return df.copy()
    out = df.resample(f"{minutes}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna(subset=["open"])


def candle_color(o: float, c: float) -> str:
    """Taiwan convention: red = up, green = down."""
    return "紅" if c > o else ("綠" if c < o else "平")


def to_local_epoch(index: pd.DatetimeIndex, tz: str) -> np.ndarray:
    """Epoch seconds of the *wall clock* in tz, so the chart axis shows local time."""
    naive = index.tz_convert(tz).tz_localize(None)
    return naive.astype("datetime64[s]").astype("int64")


def build_frame(df1m: pd.DataFrame, minutes: int, start_utc: datetime) -> pd.DataFrame:
    bars = add_sma(aggregate(df1m, minutes))
    return bars[bars.index >= pd.Timestamp(start_utc)]


def payload(bars: pd.DataFrame, tz: str) -> dict:
    t = to_local_epoch(bars.index, tz)
    candles, volume = [], []
    for ts, o, h, l, c, v in zip(t, bars.open, bars.high, bars.low, bars.close, bars.volume):
        candles.append({"time": int(ts), "open": round(o, 2), "high": round(h, 2),
                        "low": round(l, 2), "close": round(c, 2)})
        volume.append({"time": int(ts), "value": float(v), "up": bool(c > o), "flat": bool(c == o)})
    mas = {}
    for p in MA_PERIODS:
        col = bars[f"ma{p}"]
        mas[str(p)] = [{"time": int(ts), "value": round(float(v), 2)}
                       for ts, v in zip(t, col) if pd.notna(v)]
    return {"candles": candles, "volume": volume, "ma": mas, "count": len(candles)}
