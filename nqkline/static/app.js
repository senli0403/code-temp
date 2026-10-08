"use strict";
const $ = (id) => document.getElementById(id);
const UP = "#ef4444", DOWN = "#22c55e", FLAT = "#8a93a3";
const MA_COLORS = { 10: "#facc15", 60: "#22d3ee", 72: "#c084fc", 100: "#fb923c" };

// ---------- chart ----------
const chart = LightweightCharts.createChart($("chart"), {
  layout: { background: { color: "#0f1115" }, textColor: "#8a93a3" },
  grid: { vertLines: { color: "#1b2029" }, horzLines: { color: "#1b2029" } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor: "#262c36" },
  timeScale: { borderColor: "#262c36", timeVisible: true, secondsVisible: false },
  autoSize: true,
});
// volume first => drawn behind the candles
const volSeries = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.72, bottom: 0 } });
const candle = chart.addCandlestickSeries({
  upColor: UP, borderUpColor: UP, wickUpColor: UP,
  downColor: DOWN, borderDownColor: DOWN, wickDownColor: DOWN,
});
candle.priceScale().applyOptions({ scaleMargins: { top: 0.06, bottom: 0.06 } });
const maSeries = {};
for (const p of [10, 60, 72, 100]) {
  maSeries[p] = chart.addLineSeries({ color: MA_COLORS[p], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
}

let lastBars = null;

function colorWord(o, c) {
  return c > o ? '<span class="red">紅K</span>' : c < o ? '<span class="green">綠K</span>' : "平盤";
}
function legendFor(time) {
  if (!lastBars) return;
  const i = lastBars.index.get(time);
  if (i === undefined) return;
  const c = lastBars.candles[i], v = lastBars.volume[i].value;
  let h = `<span>${fmtTime(c.time)}</span><span>開 <b>${c.open}</b></span><span>高 <b>${c.high}</b></span><span>低 <b>${c.low}</b></span><span>收 <b>${c.close}</b></span><span>量 <b>${v}</b></span><span>${colorWord(c.open, c.close)}</span>`;
  for (const p of activeMAs()) {
    const m = lastBars.maMap[p].get(time);
    if (m !== undefined) h += `<span style="color:${MA_COLORS[p]}">MA${p} ${m}</span>`;
  }
  $("legend").innerHTML = h;
}
chart.subscribeCrosshairMove((param) => {
  if (param.time) legendFor(param.time);
  else if (lastBars && lastBars.candles.length) legendFor(lastBars.candles[lastBars.candles.length - 1].time);
});

function fmtTime(t) {
  const d = new Date(t * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

function activeMAs() {
  return [...document.querySelectorAll(".ma-group input:checked")].map((e) => +e.value);
}
function applyMAVisibility() {
  const on = new Set(activeMAs());
  for (const p of Object.keys(maSeries)) maSeries[p].applyOptions({ visible: on.has(+p) });
}

function render(data, keepRange) {
  const range = keepRange ? chart.timeScale().getVisibleRange() : null;
  candle.setData(data.candles);
  volSeries.setData(data.volume.map((v) => ({
    time: v.time, value: v.value,
    color: v.flat ? "rgba(138,147,163,.35)" : v.up ? "rgba(239,68,68,.38)" : "rgba(34,197,94,.38)",
  })));
  for (const p of Object.keys(maSeries)) maSeries[p].setData(data.ma[p] || []);
  lastBars = {
    candles: data.candles, volume: data.volume,
    index: new Map(data.candles.map((c, i) => [c.time, i])),
    maMap: Object.fromEntries(Object.entries(data.ma).map(([p, arr]) => [p, new Map(arr.map((x) => [x.time, x.value]))])),
  };
  applyMAVisibility();
  if (range) { try { chart.timeScale().setVisibleRange(range); } catch (e) { chart.timeScale().fitContent(); } }
  else chart.timeScale().fitContent();
  if (data.candles.length) legendFor(data.candles[data.candles.length - 1].time);
}

// ---------- api ----------
async function api(path, method = "GET", body) {
  const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  let j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((j && j.detail) || `HTTP ${r.status}`);
  return j;
}
function status(msg, err) { const s = $("status"); s.textContent = msg; s.title = msg; s.className = err ? "err" : ""; }
function dateStr(d) { return d.toISOString().slice(0, 10); }

// ---------- toolbar ----------
(function initDates() {
  const end = new Date(); end.setUTCDate(end.getUTCDate() - 1);
  const start = new Date(end); start.setUTCDate(start.getUTCDate() - 4);
  $("end").value = dateStr(end); $("start").value = dateStr(start);
})();

$("btn-load").onclick = async () => {
  $("btn-load").disabled = true; status("載入中…");
  try {
    const d = await api("/api/load", "POST", { start: $("start").value, end: $("end").value, interval: $("interval").value, demo: $("demo").checked });
    render(d, false); status(`已載入 ${d.count} 根${$("interval").value}分K` + ($("demo").checked ? "(示範資料)" : ""));
  } catch (e) { status(e.message, true); alert(e.message); }
  $("btn-load").disabled = false;
};
$("btn-cost").onclick = async () => {
  status("估算中…");
  try {
    const c = await api("/api/cost", "POST", { start: $("start").value, end: $("end").value });
    status(`預估費用 約 US$${c.cost_usd.toFixed(4)}(${(c.billable_bytes / 1e6).toFixed(2)} MB)`);
  } catch (e) { status(e.message, true); alert(e.message); }
};
$("interval").onchange = async () => {
  if (!lastBars) return;
  try { render(await api("/api/bars", "POST", { interval: $("interval").value }), true); status(`已切換為 ${$("interval").value} 分K`); }
  catch (e) { status(e.message, true); }
};
document.querySelectorAll(".ma-group input").forEach((e) => (e.onchange = () => { applyMAVisibility(); if (lastBars) legendFor(lastBars.candles[lastBars.candles.length - 1].time); }));

// ---------- chat ----------
function esc(s) { return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function md(s) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(紅K)/g, '<span class="red">$1</span>').replace(/(綠K)/g, '<span class="green">$1</span>');
}
function addMsg(role, text, time) {
  const el = document.createElement("div");
  el.className = "m " + (role === "user" ? "user" : "ai");
  el.innerHTML = (role === "user" ? esc(text) : md(text)) + (time ? `<small>${time}</small>` : "");
  $("chat").appendChild(el); $("chat").scrollTop = $("chat").scrollHeight;
  return el;
}
async function send() {
  const text = $("msg").value.trim();
  if (!text) return;
  if (!lastBars) { addMsg("ai", "請先按上方「查詢」載入K線資料,我才看得到圖。"); return; }
  $("msg").value = ""; addMsg("user", text);
  const pending = addMsg("ai", "思考中…"); pending.classList.add("pending");
  $("btn-send").disabled = true;
  const vr = chart.timeScale().getVisibleRange();
  try {
    const r = await api("/api/chat", "POST", { message: text, interval: $("interval").value, mas: activeMAs(), t_from: vr ? vr.from : null, t_to: vr ? vr.to : null });
    pending.classList.remove("pending"); pending.innerHTML = md(r.reply);
  } catch (e) { pending.classList.remove("pending"); pending.innerHTML = '<span class="red">' + esc(e.message) + "</span>"; }
  $("btn-send").disabled = false; $("chat").scrollTop = $("chat").scrollHeight;
}
$("btn-send").onclick = send;
$("msg").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
$("btn-clear").onclick = async () => { if (confirm("清除所有對話紀錄?(AI 筆記不會被刪除)")) { await api("/api/chat/history", "DELETE"); $("chat").innerHTML = ""; } };
(async () => { try { for (const m of await api("/api/chat/history")) addMsg(m.role, m.content, m.time); } catch (e) {} })();

// ---------- modals ----------
function openModal(html) { $("modal-card").innerHTML = html; $("modal").classList.remove("hidden"); }
function closeModal() { $("modal").classList.add("hidden"); }
$("modal").onclick = (e) => { if (e.target === $("modal")) closeModal(); };

$("btn-settings").onclick = async () => {
  const c = await api("/api/config");
  const tzs = ["Asia/Taipei", "America/New_York", "America/Chicago", "UTC"];
  openModal(`<h3>設定</h3>
    <label>Databento API Key ${c.databento_key_set ? `<span class="hint">(已設定 ${c.databento_key_hint},留空表示不變)</span>` : ""}</label>
    <input id="s-db" type="password" placeholder="db-..." autocomplete="off">
    <label>Anthropic (Claude) API Key ${c.anthropic_key_set ? `<span class="hint">(已設定 ${c.anthropic_key_hint},留空表示不變)</span>` : ""}</label>
    <input id="s-an" type="password" placeholder="sk-ant-..." autocomplete="off">
    <label>Claude 模型</label><input id="s-model" value="${esc(c.model)}">
    <label>顯示時區(日期範圍與K棒時間皆依此時區)</label>
    <select id="s-tz">${tzs.map((z) => `<option ${z === c.timezone ? "selected" : ""}>${z}</option>`).join("")}</select>
    <p class="hint">標的:${esc(c.symbol)}(${esc(c.dataset)},CME NQ 近月連續合約)。金鑰只存放在你電腦的使用者資料夾。</p>
    <div class="actions"><button onclick="closeModal()">取消</button><button class="primary" id="s-save">儲存</button></div>`);
  $("s-save").onclick = async () => {
    await api("/api/config", "POST", { databento_key: $("s-db").value, anthropic_key: $("s-an").value, model: $("s-model").value, timezone: $("s-tz").value });
    closeModal(); status("設定已儲存(時區變更需重新按「查詢」)");
  };
};
async function showNotes() {
  const notes = await api("/api/notes");
  openModal(`<h3>AI 筆記(它從你這裡學到的技術)</h3>` +
    (notes.length ? notes.map((n) => `<div class="note"><div><b>${esc(n.title)}</b><br>${esc(n.content)}<br><small>${n.created}</small></div><button data-id="${n.id}">刪除</button></div>`).join("") : '<p class="hint">還沒有筆記。在對話框教它技術並說「記住」,它就會存在這裡。</p>') +
    '<div class="actions"><button class="primary" onclick="closeModal()">關閉</button></div>');
  document.querySelectorAll(".note button").forEach((b) => (b.onclick = async () => { await api("/api/notes/" + b.dataset.id, "DELETE"); showNotes(); }));
}
$("btn-notes").onclick = showNotes;
