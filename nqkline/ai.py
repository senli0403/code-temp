"""Claude chat: sees the visible bars (with red/green candle labels) and keeps the user's taught rules."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pandas as pd

from . import config
from .data import candle_color, to_local_epoch

MAX_BARS = 150
MAX_HISTORY_TURNS = 20
MAX_TOOL_ROUNDS = 4

SAVE_NOTE_TOOL = {
    "name": "save_note",
    "description": ("把使用者教你的技術分析觀念、判斷規則或偏好存進長期筆記,之後每次對話都會自動帶入。"
                    "只在使用者明確在教你新規則、或要求你「記住」時使用。內容要精簡、可操作,一則筆記只講一件事。"),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "筆記標題,例如「均線多頭排列」"},
            "content": {"type": "string", "description": "規則內容,盡量包含判斷條件與結論"},
        },
        "required": ["title", "content"],
    },
}


# ---------- notes & history ----------
def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path, data):
    config.ensure_dirs()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def list_notes() -> list[dict]:
    return _read(config.NOTES_FILE, [])


def add_note(title: str, content: str) -> dict:
    notes = list_notes()
    note = {"id": uuid.uuid4().hex[:8], "title": title.strip(), "content": content.strip(),
            "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
    notes.append(note)
    _write(config.NOTES_FILE, notes)
    return note


def delete_note(note_id: str) -> None:
    _write(config.NOTES_FILE, [n for n in list_notes() if n["id"] != note_id])


def history() -> list[dict]:
    return _read(config.HISTORY_FILE, [])


def clear_history() -> None:
    _write(config.HISTORY_FILE, [])


# ---------- prompt building ----------
def bars_table(bars: pd.DataFrame, tz: str, interval: int) -> str:
    """Compact text table of the bars the user is looking at."""
    bars = bars.tail(MAX_BARS)
    if bars.empty:
        return "(目前畫面沒有K棒)"
    stamps = pd.to_datetime(to_local_epoch(bars.index, tz), unit="s")
    lines = [f"時間({tz}),開,高,低,收,量,K色,MA10,MA60,MA72,MA100"]

    def f(v):
        return "" if pd.isna(v) else f"{v:.2f}"

    for ts, r in zip(stamps, bars.itertuples()):
        lines.append(",".join([ts.strftime("%m-%d %H:%M"), f(r.open), f(r.high), f(r.low), f(r.close),
                               str(int(r.volume)), candle_color(r.open, r.close),
                               f(r.ma10), f(r.ma60), f(r.ma72), f(r.ma100)]))
    return "\n".join(lines)


def system_prompt(cfg: dict, interval: int, active_mas: list[int]) -> str:
    notes = list_notes()
    notes_txt = "\n".join(f"- 【{n['title']}】{n['content']}" for n in notes) or "(目前還沒有筆記)"
    return f"""你是使用者的那斯達克(NQ 期貨,Databento 連續合約 {cfg['symbol']})技術分析助理,使用繁體中文回答。

# 圖表約定
- 台灣慣例:**紅K = 收盤高於開盤(上漲)**,**綠K = 收盤低於開盤(下跌)**,「平」代表開收相同。
- 使用者當前看的是 {interval} 分K,畫面上勾選的均線:{', '.join('MA'+str(m) for m in active_mas) or '無'}。
- 每則訊息會附上使用者畫面中的K棒資料(時間為 {cfg['timezone']} 當地時間),欄位含紅/綠K標記與各條均線數值。回答時請引用實際的時間與價位,不要憑空編造數據。
- 價格為連續合約,換月處可能有跳空,請留意。

# 使用者教你的技術(長期筆記)
{notes_txt}

# 行為準則
- 分析時優先套用上面的筆記規則,並說明你用了哪一條。
- 當使用者在教你新的判斷方法或要求你記住某件事,呼叫 save_note 工具存下來,再簡短確認。
- 你提供的是技術面解讀,不是投資建議;不要保證漲跌,必要時指出不確定性與風險。
- 回答精簡、條列清楚。"""


# ---------- chat ----------
def chat(cfg: dict, message: str, bars_text: str, interval: int, active_mas: list[int]) -> str:
    import anthropic

    if not cfg["anthropic_key"]:
        raise RuntimeError("尚未設定 Anthropic API Key,請按右上角「設定」填入。")
    client = anthropic.Anthropic(api_key=cfg["anthropic_key"])

    hist = history()
    api_msgs = [{"role": m["role"], "content": m["content"]} for m in hist[-2 * MAX_HISTORY_TURNS:]]
    user_content = f"{message}\n\n[目前畫面K棒資料]\n{bars_text}"
    api_msgs.append({"role": "user", "content": user_content})
    system = system_prompt(cfg, interval, active_mas)

    text_out = ""
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(model=cfg["model"], max_tokens=2000, system=system,
                                      tools=[SAVE_NOTE_TOOL], messages=api_msgs)
        text_out += "".join(b.text for b in resp.content if b.type == "text")
        if resp.stop_reason != "tool_use":
            break
        api_msgs.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type == "tool_use" and b.name == "save_note":
                note = add_note(b.input.get("title", "筆記"), b.input.get("content", ""))
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": f"已儲存筆記 {note['id']}"})
                text_out += f"\n\n📝 已記住:【{note['title']}】\n"
            elif b.type == "tool_use":
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": "未知工具", "is_error": True})
        api_msgs.append({"role": "user", "content": results})

    text_out = text_out.strip() or "(沒有回覆內容)"
    stamp = datetime.now().strftime("%H:%M")
    hist.append({"role": "user", "content": message, "time": stamp})
    hist.append({"role": "assistant", "content": text_out, "time": stamp})
    _write(config.HISTORY_FILE, hist[-200:])
    return text_out
