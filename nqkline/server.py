import sys
import threading
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, config, data
from .data import DataError


def static_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "nqkline" / "static"


app = FastAPI(title="NQ K線分析")
_state = {"lock": threading.Lock(), "df1m": None, "start_utc": None, "cfg_tz": None}


class LoadReq(BaseModel):
    start: date
    end: date
    interval: str = "5"
    demo: bool = False


class BarsReq(BaseModel):
    interval: str = "5"


class CostReq(BaseModel):
    start: date
    end: date


class ChatReq(BaseModel):
    message: str
    interval: str = "5"
    mas: list[int] = []
    t_from: int | None = None  # visible range, chart (local wall-clock) epoch seconds
    t_to: int | None = None


class ConfigReq(BaseModel):
    databento_key: str | None = None
    anthropic_key: str | None = None
    model: str | None = None
    timezone: str | None = None


def _minutes(interval: str) -> int:
    if interval not in data.INTERVALS:
        raise HTTPException(400, "不支援的K線週期")
    return data.INTERVALS[interval]


def _frame(interval: str) -> pd.DataFrame:
    if _state["df1m"] is None:
        raise HTTPException(400, "請先按「查詢」載入資料")
    return data.build_frame(_state["df1m"], _minutes(interval), _state["start_utc"])


@app.get("/api/config")
def get_config():
    return config.public(config.load())


@app.post("/api/config")
def set_config(req: ConfigReq):
    return config.public(config.save(req.model_dump()))


@app.post("/api/cost")
def cost(req: CostReq):
    cfg = config.load()
    s, e = data.utc_range(req.start, req.end, cfg["timezone"])
    try:
        return data.estimate_cost(cfg, s - pd.Timedelta(days=data.WARMUP_DAYS), e)
    except DataError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/load")
def load(req: LoadReq):
    cfg = config.load()
    if req.end < req.start:
        raise HTTPException(400, "結束日不可早於開始日")
    s, e = data.utc_range(req.start, req.end, cfg["timezone"])
    try:
        if req.demo:
            df = data.demo_1m(s - pd.Timedelta(days=data.WARMUP_DAYS), e)
        else:
            df = data.fetch_1m(cfg, s - pd.Timedelta(days=data.WARMUP_DAYS), e)
    except DataError as exc:
        raise HTTPException(400, str(exc))
    with _state["lock"]:
        _state.update(df1m=df, start_utc=s, cfg_tz=cfg["timezone"])
    return data.payload(_frame(req.interval), cfg["timezone"])


@app.post("/api/bars")
def bars(req: BarsReq):
    return data.payload(_frame(req.interval), _state["cfg_tz"] or config.load()["timezone"])


@app.post("/api/chat")
def chat(req: ChatReq):
    cfg = config.load()
    minutes = _minutes(req.interval)
    frame = _frame(req.interval)
    tz = _state["cfg_tz"] or cfg["timezone"]
    if req.t_from is not None and req.t_to is not None:
        t = data.to_local_epoch(frame.index, tz)
        frame = frame[(t >= req.t_from) & (t <= req.t_to)]
    try:
        reply = ai.chat(cfg, req.message, ai.bars_table(frame, tz, minutes), minutes, req.mas)
    except Exception as exc:  # surface API / key errors to the chat pane
        raise HTTPException(400, f"AI 呼叫失敗:{exc}")
    return {"reply": reply}


@app.get("/api/chat/history")
def chat_history():
    return ai.history()


@app.delete("/api/chat/history")
def chat_clear():
    ai.clear_history()
    return {"ok": True}


@app.get("/api/notes")
def notes():
    return ai.list_notes()


@app.delete("/api/notes/{note_id}")
def note_delete(note_id: str):
    ai.delete_note(note_id)
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(static_dir() / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


app.mount("/static", StaticFiles(directory=static_dir()), name="static")
