// ── tema ──────────────────────────────────────────────
const root = document.documentElement;
const savedTheme = localStorage.getItem("theme") || "dark";
root.setAttribute("data-theme", savedTheme);
document.getElementById("themeBtn").onclick = () => {
  const t = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", t); localStorage.setItem("theme", t);
};

// ── tabs ──────────────────────────────────────────────
const tabs = document.querySelectorAll(".tab");
tabs.forEach(b => b.onclick = () => {
  tabs.forEach(x => x.classList.remove("is-active"));
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("is-active"));
  b.classList.add("is-active");
  document.getElementById("tab-" + b.dataset.tab).classList.add("is-active");
  if (b.dataset.tab === "signals") loadSignals();
  if (b.dataset.tab === "universe") loadUniverse();
  if (b.dataset.tab === "agent") { loadAgent(); startAgentPoll(); }
  if (b.dataset.tab === "admin") initAdmin();
  if (b.dataset.tab !== "agent") stopAgentPoll();
});
const AGENT_POLL_MS = 1000;   // refresh dry-run tiap 1 dtk (harga terkini di-cache 3s server-side;
                              // monitor menjalankan step tiap 20s — jadi fill/funding muncul otomatis)
let _agentTimer = null, _agentLive = true;
function startAgentPoll() { stopAgentPoll(); if (_agentLive) _agentTimer = setInterval(() => loadAgent(true), AGENT_POLL_MS); }
function stopAgentPoll() { if (_agentTimer) { clearInterval(_agentTimer); _agentTimer = null; } }

// ── util ──────────────────────────────────────────────
const esc = s => String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const fmtUsd = n => n == null ? "—" : (Math.abs(n) >= 1e9 ? (n / 1e9).toFixed(1) + "B" : Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(0) + "M" : Math.abs(n) >= 1e3 ? (n / 1e3).toFixed(0) + "k" : n.toFixed(0));
// Angka utama (significant figures): harga >=$1000 -> 5 sig-fig; <$1000 -> 4 sig-fig.
// Contoh: BTC 60130, ETH 1630.5, SOL 77.67, UNI 3.055, SUI 0.7239.
function fmtPrice(p) {
  if (p == null || isNaN(p)) return "—";
  const a = Math.abs(p);
  if (a === 0) return "0";
  const sig = a >= 1000 ? 5 : 4;
  const d = sig - 1 - Math.floor(Math.log10(a));
  if (d <= 0) { const f = Math.pow(10, d); return String(Math.round(p * f) / f); }
  return p.toFixed(d);
}
function fmtQty(q) {
  if (q == null || isNaN(q)) return "—";
  const a = Math.abs(q);
  if (a === 0) return "0";
  if (a >= 1000) return Math.round(q).toLocaleString("en-US");           // 50123.4 -> "50,123"
  const d = Math.max(0, 5 - 1 - Math.floor(Math.log10(a)));              // 5 angka penting
  return q.toFixed(d).replace(/\.?0+$/, "");                            // 115.740741 -> "115.74"
}
// arah trade ringkas: L hijau (long) / S merah (short), tebal
const legTag = leg => leg === "long" ? '<b class="pos">L</b>' : '<b class="neg">S</b>';
function md(src) {
  const lines = (src || "").split("\n"); let html = "", inUl = false, inTbl = false;
  const closeUl = () => { if (inUl) { html += "</ul>"; inUl = false; } };
  const closeTbl = () => { if (inTbl) { html += "</table>"; inTbl = false; } };
  const inline = t => esc(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>");
  for (let raw of lines) {
    const l = raw.trim();
    if (!l) { closeUl(); closeTbl(); continue; }
    if (/^\|(.+)\|$/.test(l)) {
      if (/^\|[\s:|-]+\|$/.test(l)) continue;
      if (!inTbl) { html += "<table>"; inTbl = true; }
      const cells = l.slice(1, -1).split("|").map(c => c.trim());
      const tag = inTbl && html.indexOf("<table>") === html.lastIndexOf("<table>") && !html.includes("</tr>") ? "th" : "td";
      html += "<tr>" + cells.map(c => `<${tag}>${inline(c)}</${tag}>`).join("") + "</tr>";
      continue;
    } else closeTbl();
    if (/^#{1,3}\s/.test(l)) { closeUl(); const n = l.match(/^#+/)[0].length; html += `<h${n}>${inline(l.replace(/^#+\s/, ""))}</h${n}>`; }
    else if (/^[-*]\s/.test(l)) { if (!inUl) { html += "<ul>"; inUl = true; } html += `<li>${inline(l.replace(/^[-*]\s/, ""))}</li>`; }
    else if (/^---+$/.test(l)) { closeUl(); html += "<hr>"; }
    else { closeUl(); html += `<p>${inline(l)}</p>`; }
  }
  closeUl(); closeTbl(); return html;
}

// ── tabel collapsible + paginasi (10/hal) ──────────────
const _pgt = {};
const PG_PER = 10;
function _pgInner(id) {
  const t = _pgt[id];
  const n = t.rows.length, pages = Math.max(1, Math.ceil(n / t.per));
  if (t.page >= pages) t.page = pages - 1;
  if (t.page < 0) t.page = 0;
  const slice = t.rows.slice(t.page * t.per, t.page * t.per + t.per);
  const nav = pages > 1 ? `<div class="pager"><button class="ctab" onclick="pgGo('${id}',-1)"${t.page <= 0 ? " disabled" : ""}>‹ Sebelumnya</button><span class="muted">Hal ${t.page + 1}/${pages} · ${n} total</span><button class="ctab" onclick="pgGo('${id}',1)"${t.page >= pages - 1 ? " disabled" : ""}>Berikutnya ›</button></div>` : "";
  const inner = t.cardFn
    ? `<div class="pos-cards">${slice.map(t.cardFn).join("")}</div>`
    : `<div class="dtable-wrap"><table class="dtable"><thead>${t.thead}</thead><tbody>${slice.map(t.rowFn).join("")}</tbody></table></div>`;
  return inner + nav;
}
function pgGo(id, d) {
  const t = _pgt[id]; if (!t) return;
  const pages = Math.max(1, Math.ceil(t.rows.length / t.per));
  t.page = Math.min(pages - 1, Math.max(0, t.page + d));
  const w = document.getElementById("pgw-" + id); if (w) w.innerHTML = _pgInner(id);
}
function pgToggle(id, isOpen) { if (_pgt[id]) _pgt[id].open = isOpen; }
function pagedTable(id, title, thead, rows, rowFn, opts) {
  opts = opts || {};
  const prev = _pgt[id];
  _pgt[id] = { rows, rowFn, page: prev ? prev.page : 0, per: opts.per || PG_PER, thead, open: prev ? prev.open : (opts.open !== false) };
  return `<details class="guide"${_pgt[id].open ? " open" : ""} style="margin-top:12px" ontoggle="pgToggle('${id}',this.open)"><summary>${title} (${rows.length})</summary><div class="guide-body"><div id="pgw-${id}">${_pgInner(id)}</div></div></details>`;
}
// paginasi KARTU. opts.collapsible=true -> bisa minimize/maximize (<details>); else selalu tampil.
function pagedCards(id, title, items, cardFn, opts) {
  opts = opts || {};
  const prev = _pgt[id];
  _pgt[id] = { rows: items, cardFn, page: prev ? prev.page : 0, per: opts.per || 5, open: prev ? prev.open : (opts.open !== false) };
  const body = `<div id="pgw-${id}">${_pgInner(id)}</div>`;
  if (opts.collapsible) {
    return `<details class="guide"${_pgt[id].open ? " open" : ""} style="margin-top:12px" ontoggle="pgToggle('${id}',this.open)"><summary>${esc(title)} (${items.length})</summary><div class="guide-body">${body}</div></details>`;
  }
  return `<div class="ag-open-sec"><h3 class="ag-h">${esc(title)} (${items.length})</h3>${body}</div>`;
}

// ── modal konfirmasi (type-to-confirm) ─────────────────
function confirmAction({ title, body, word, btnLabel, danger }) {
  return new Promise(resolve => {
    if (document.getElementById("cfModal")) return resolve(null);
    const ov = document.createElement("div");
    ov.id = "cfModal"; ov.className = "modal-ov";
    ov.innerHTML = `<div class="modal-card" role="dialog" aria-modal="true">
      <h3 class="modal-h">${title}</h3>${body}
      <p class="modal-p">Untuk melanjutkan, ketik <b>${word}</b> (huruf besar) di bawah:</p>
      <input id="cfWord" class="modal-input" placeholder="ketik ${word}" autocomplete="off" spellcheck="false">
      <div id="cfErr" class="modal-err"></div>
      <div class="modal-actions">
        <button id="cfCancel" class="btn-ghost">Batal</button>
        <button id="cfGo" class="${danger ? "btn-danger" : "btn-primary"}" disabled>${btnLabel}</button>
      </div></div>`;
    document.body.appendChild(ov);
    const inp = ov.querySelector("#cfWord"), go = ov.querySelector("#cfGo");
    const close = (v) => { ov.remove(); resolve(v); };
    setTimeout(() => inp.focus(), 30);
    inp.oninput = () => { go.disabled = inp.value.trim() !== word; };
    inp.onkeydown = e => { if (e.key === "Enter" && !go.disabled) go.click(); if (e.key === "Escape") close(null); };
    ov.querySelector("#cfCancel").onclick = () => close(null);
    ov.onclick = e => { if (e.target === ov) close(null); };
    go.onclick = () => { go.disabled = true; close(inp.value.trim()); };
  });
}

// ── confluence gauge (-4..+4) ──────────────────────────
function gauge(score) {
  const v = Math.max(-4, Math.min(4, score || 0));
  const pct = Math.abs(v) / 4 * 50;
  const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
  const fillStyle = v >= 0 ? `left:50%;width:${pct}%` : `right:50%;width:${pct}%`;
  return `<div class="gauge"><div class="gauge-track"><div class="gauge-mid"></div><div class="gauge-fill ${cls}" style="${fillStyle}"></div></div><div class="gauge-val ${cls}">${v > 0 ? "+" : ""}${v}</div></div>`;
}
function legBadges(c) {
  const legs = [["FVG", c.fvg_score], ["Fib", c.fib_score], ["OI", c.oi_score], ["FR", c.fr_score]];
  return `<div class="leg-badges">${legs.map(([n, v]) => {
    const cls = v > 0 ? "pos" : v < 0 ? "neg" : "zero";
    return `<span class="leg-badge ${cls}">${n} ${v > 0 ? "+" : ""}${v ?? 0}</span>`;
  }).join("")}</div>`;
}
function zoneChip(z) { return z ? `<span class="zone-chip ${esc(z)}">${esc(z)}</span>` : ""; }

// ── status ────────────────────────────────────────────
(async () => {
  try {
    const d = await (await fetch("/api/doctor")).json();
    const el = document.getElementById("status");
    el.textContent = `${d.tokens} koin · dry-run`;
    el.classList.add("ok");
    el.title = `posisi terbuka: ${d.open_positions} · LLM ${d.llm_configured ? "siap" : "belum diset"}`;
  } catch { document.getElementById("status").textContent = "offline"; }
})();

// ── Analisa ───────────────────────────────────────────
let _activeSym = null;
document.getElementById("searchForm").onsubmit = e => { e.preventDefault(); document.getElementById("symSuggest").classList.remove("show"); analyze(document.getElementById("symInput").value.trim()); };

// ── suggest/autocomplete simbol (Analisa) — dari universe ──
let _symList = [];
async function _loadSymList() {
  if (_symList.length) return _symList;
  try { const d = await (await fetch("/api/universe")).json(); _symList = (d.tokens || []).map(t => ({ symbol: t.symbol, name: t.name || "" })); } catch { /* offline */ }
  return _symList;
}
function _renderSuggest(q) {
  const box = document.getElementById("symSuggest");
  q = (q || "").trim().toUpperCase();
  const m = q ? _symList.filter(t => t.symbol.includes(q) || t.name.toUpperCase().includes(q)).slice(0, 8) : [];
  if (!m.length) { box.innerHTML = ""; box.classList.remove("show"); return; }
  box.innerHTML = m.map(t => `<div class="sug-item" data-sym="${esc(t.symbol)}"><b>${esc(t.symbol)}</b> <span class="muted">${esc(t.name)}</span></div>`).join("");
  box.classList.add("show");
  box.querySelectorAll(".sug-item").forEach(el => el.onmousedown = ev => {
    ev.preventDefault(); const s = el.dataset.sym;
    document.getElementById("symInput").value = s; box.classList.remove("show"); analyze(s);
  });
}
(function initSuggest() {
  const inp = document.getElementById("symInput"); if (!inp) return;
  _loadSymList();
  inp.addEventListener("input", () => _renderSuggest(inp.value));
  inp.addEventListener("focus", () => { _loadSymList(); _renderSuggest(inp.value); });
  inp.addEventListener("blur", () => setTimeout(() => document.getElementById("symSuggest").classList.remove("show"), 150));
  inp.addEventListener("keydown", ev => { if (ev.key === "Escape") document.getElementById("symSuggest").classList.remove("show"); });
})();

function _confluenceSection(title, d) {
  if (!d || d.error) return `<div class="confluence-card"><h4>${title}</h4><p class="muted">${d && d.error ? esc(d.error) : "tak ada data"}</p></div>`;
  const c = d.confluence || {};
  const verdict = d.action === "open" ? `<span class="verdict-badge open">OPEN ${d.direction > 0 ? "LONG" : "SHORT"}</span>` : `<span class="verdict-badge skip">SKIP</span>`;
  let body = `<div class="confluence-card"><h4>${title}</h4>
    <div class="row-l" style="display:flex;justify-content:space-between;align-items:center">${verdict}${zoneChip(d.zone || c.zone)}</div>
    ${gauge(d.full_score != null ? d.full_score : c.full_score)}
    ${legBadges(c.full_score != null ? c : d)}`;
  if (d.action === "open") {
    body += `<div class="ac-grid" style="margin-top:10px">
      <div><span>Entry</span><b>${fmtPrice(d.entry)}</b></div>
      <div><span>SL</span><b class="neg">${fmtPrice(d.sl)}</b></div>
      <div><span>Leverage</span><b>${d.leverage}x</b></div>
      <div><span>Risk</span><b>$${(d.risk_usd || 0).toFixed(2)} (${((d.risk_frac || 0) * 100).toFixed(2)}%)</b></div>
    </div>
    <div class="tp-ladder">${(d.tps || []).map(t => `<div class="tp-step" title="${t.label} ${t.price ? fmtPrice(t.price) : "—"} (${(t.frac * 100).toFixed(0)}%)"></div>`).join("")}</div>
    <div class="tp-labels">${(d.tps || []).map(t => `<span>${t.label}</span>`).join("")}</div>`;
  } else {
    body += `<p class="muted" style="margin-top:8px">Alasan: ${esc(d.reason || "—")}</p>`;
  }
  body += `</div>`;
  return body;
}

// ── CHART VISUAL (lightweight-charts): candle + FVG/OB boxes + fib/struktur + liquidity + toggles ──
let _lwChart = null, _lwCandle = null, _lwVol = null, _chartData = null, _chartDecs = 2, _chartTf = "1h";
let _priceLines = [];
const _ind = { fvg: true, fib: true, ob: true, struct: true, liq: true, vol: true };  // saklar indikator
let _obFilter = "all";   // saklar Order Block: all | demand | supply (hindari tumpang-tindih demand/supply)
const _obShow = o => _obFilter === "all" || (_obFilter === "demand") === (o.type === "bull");
function _chartCols() {
  const dark = document.documentElement.getAttribute("data-theme") !== "light";
  return { text: dark ? "#93a1b0" : "#556", grid: dark ? "rgba(255,255,255,.05)" : "rgba(0,0,0,.05)" };
}
// jumlah desimal presisi berdasar besaran harga (BTC 2, koin murah 0.08867 -> 5+)
function _decsFor(a) { a = Math.abs(a || 1); return a >= 1000 ? 2 : a >= 1 ? 3 : a >= 0.1 ? 4 : a >= 0.01 ? 5 : a >= 0.001 ? 6 : a >= 0.0001 ? 7 : 8; }
function _cp(p) { return p == null || isNaN(p) ? "—" : (+p).toFixed(_chartDecs); }   // harga presisi-penuh chart
async function renderChart(sym, tf) {
  _chartTf = tf;
  document.getElementById("chartWrap").hidden = false;
  document.getElementById("chartSym").innerHTML = `<b>${esc(sym)}</b> <span class="muted">· ${tf}</span>`;
  document.querySelectorAll("#tfTabs button").forEach(b => b.classList.toggle("on", b.dataset.tf === tf));
  const holder = document.getElementById("chart");
  holder.innerHTML = `<div class="loading" style="padding:40px"><div class="spinner"></div> memuat chart…</div>`;
  if (!window.LightweightCharts) { holder.innerHTML = `<p class="muted" style="padding:20px">library chart gagal dimuat</p>`; return; }
  let d;
  try { d = await (await fetch(`/api/chart/${encodeURIComponent(sym)}?tf=${tf}`)).json(); }
  catch { holder.innerHTML = `<p class="muted" style="padding:20px">gagal memuat chart</p>`; return; }
  if (!d.ok) { holder.innerHTML = `<p class="muted" style="padding:20px">${esc(d.error || "gagal")}</p>`; return; }
  holder.innerHTML = "";
  if (_lwChart) { try { _lwChart.remove(); } catch (e) { /* */ } _lwChart = null; }
  _chartData = d; _priceLines = [];
  _chartDecs = _decsFor((d.candles[d.candles.length - 1] || {}).close);
  const col = _chartCols();
  const chart = LightweightCharts.createChart(holder, {
    layout: { background: { type: "solid", color: "transparent" }, textColor: col.text, fontSize: 11 },
    grid: { vertLines: { color: col.grid }, horzLines: { color: col.grid } },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: "rgba(128,128,128,.3)" },
    rightPriceScale: { borderColor: "rgba(128,128,128,.3)" }, crosshair: { mode: 1 },
    width: holder.clientWidth, height: 430,
  });
  const dec = _chartDecs;
  const cs = chart.addCandlestickSeries({
    upColor: "#26a69a", downColor: "#ef5350", borderVisible: false, wickUpColor: "#26a69a", wickDownColor: "#ef5350",
    priceFormat: { type: "custom", minMove: Math.pow(10, -dec), formatter: p => (+p).toFixed(dec) },  // presisi harga asli
  });
  cs.setData(d.candles);
  const vs = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.86, bottom: 0 } });
  vs.setData(d.volume);
  _lwChart = chart; _lwCandle = cs; _lwVol = vs;
  const draw = () => _drawBoxes();
  chart.timeScale().subscribeVisibleTimeRangeChange(draw);
  chart.timeScale().subscribeVisibleLogicalRangeChange(draw);
  try { new ResizeObserver(() => { chart.applyOptions({ width: holder.clientWidth }); draw(); }).observe(holder); } catch (e) { /* */ }
  chart.timeScale().fitContent();
  _applyOverlays();
  setTimeout(draw, 80);
  _renderIndicatorPanel(d);
}
// gambar/ulang overlay sesuai saklar (_ind) — TANPA hilang zoom
function _applyOverlays() {
  const cs = _lwCandle, d = _chartData; if (!cs || !d) return;
  _priceLines.forEach(l => { try { cs.removePriceLine(l); } catch (e) { /* */ } }); _priceLines = [];
  const pl = (price, color, title, style) => { if (price != null) _priceLines.push(cs.createPriceLine({ price: +price, color, lineWidth: 1, lineStyle: style ?? 2, axisLabelVisible: true, title: title || "" })); };
  const fib = d.fib || {};
  if (_ind.fib) {
    if (fib.swing_high && fib.swing_high.price != null) pl(fib.swing_high.price, "#e6b800", "SwH · fib 0", 0);  // anchor
    if (fib.swing_low && fib.swing_low.price != null) pl(fib.swing_low.price, "#e6b800", "SwL · fib 1", 0);
    if (fib.golden_pocket) { pl(fib.golden_pocket[0], "#e6b800", "GP", 0); pl(fib.golden_pocket[1], "#e6b800", ""); }
    if (fib.ote) { pl(fib.ote[0], "#c792ea", "OTE"); pl(fib.ote[1], "#c792ea", ""); }
    if (fib.equilibrium) pl(fib.equilibrium, "rgba(128,128,128,.55)", "EQ 0.5");
  }
  const st = d.structure || {};
  if (_ind.struct) { pl(st.last_swing_high, "rgba(239,83,80,.5)", "SwH"); pl(st.last_swing_low, "rgba(38,166,154,.5)", "SwL"); }
  if (_ind.liq) {
    const lq = d.liquidity || {};
    (lq.bsl || []).forEach(b => pl(b.level, b.eq ? "#ff9800" : "rgba(255,152,0,.5)", b.eq ? "EQH" : "BSL", b.eq ? 0 : 2));
    (lq.ssl || []).forEach(s => pl(s.level, s.eq ? "#ff9800" : "rgba(255,152,0,.5)", s.eq ? "EQL" : "SSL", s.eq ? 0 : 2));
    if (lq.sweep && lq.sweep.swept && lq.sweep.level != null) pl(lq.sweep.level, "#ff5252", `SWEEP ${lq.sweep.type || ""} ${lq.sweep.direction > 0 ? "↑" : "↓"}`, 0);
  }
  cs.setMarkers(_ind.struct ? (d.swings || []).map(s => ({ time: s.time, position: s.kind === "high" ? "aboveBar" : "belowBar", color: s.kind === "high" ? "#ef5350" : "#26a69a", shape: s.provisional ? "circle" : (s.kind === "high" ? "arrowDown" : "arrowUp"), text: (s.kind === "high" ? "H" : "L") + (s.provisional ? "?" : "") })) : []);
  if (_lwVol) _lwVol.applyOptions({ visible: _ind.vol });
  _drawBoxes();
}
function _drawBoxes() {
  const chart = _lwChart, cs = _lwCandle, d = _chartData, canvas = document.getElementById("chartCanvas");
  if (!chart || !cs || !d || !canvas) return;
  const holder = canvas.parentElement;
  const w = holder.clientWidth, h = holder.clientHeight, dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = w + "px"; canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  const ts = chart.timeScale();
  const box = (from, top, bottom, fill, stroke, label) => {
    let x1 = ts.timeToCoordinate(from); if (x1 == null) x1 = 0; x1 = Math.max(0, x1);
    const y1 = cs.priceToCoordinate(+top), y2 = cs.priceToCoordinate(+bottom);
    if (y1 == null || y2 == null) return;
    const yy = Math.min(y1, y2), hh = Math.abs(y2 - y1);
    ctx.fillStyle = fill; ctx.fillRect(x1, yy, w - x1, hh);
    ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.strokeRect(x1, yy, w - x1, hh);
    if (label && hh >= 9) { ctx.fillStyle = stroke; ctx.font = "9px system-ui,sans-serif"; ctx.fillText(label, x1 + 3, yy + hh / 2 + 3); }
  };
  if (_ind.fvg) (d.fvg || []).forEach(f => { const b = f.direction === "bullish"; box(f.from, f.top, f.bottom, b ? "rgba(38,166,154,.09)" : "rgba(239,83,80,.09)", b ? "rgba(38,166,154,.5)" : "rgba(239,83,80,.5)", b ? "FVG↑" : "FVG↓"); });
  if (_ind.ob) (d.order_blocks || []).forEach(o => { if (!_obShow(o)) return; const b = o.type === "bull", fresh = o.status !== "mitigated"; box(o.from, o.top, o.bottom, b ? (fresh ? "rgba(66,165,245,.14)" : "rgba(66,165,245,.05)") : (fresh ? "rgba(255,167,38,.14)" : "rgba(255,167,38,.05)"), b ? "rgba(66,165,245,.6)" : "rgba(255,167,38,.6)", (o.akum ? (b ? "AKUM ⌂ support" : "DIST ⌂ resist") : (b ? "OB↑ demand" : "OB↓ supply")) + (o.vol ? " ✓vol" : "") + (o.retests > 1 ? " ×" + o.retests : "") + (o.flip ? " ⇄flip" : "")); });
}
// panel indikator: saklar checkbox bernama + detail AREA HARGA tiap deteksi
function _renderIndicatorPanel(d) {
  const c = d.confluence || {}, sc = c.full_score;
  const chip = (t, cls) => `<span class="cl-chip ${cls || ""}">${t}</span>`;
  const conf = chip(`score ${sc > 0 ? "+" : ""}${sc ?? "?"}`, sc > 0 ? "pos" : sc < 0 ? "neg" : "") +
    chip(`zona ${esc(c.zone || "?")}`) + (c.high_confluence ? chip("A+ confluence", "pos") : "") +
    chip(`vol ${esc(c.vol_state || "?")}`) + (c.rsi != null ? chip(`RSI ${c.rsi}`) : "");
  const fib = d.fib || {}, st = d.structure || {}, lq = d.liquidity || {};
  const fvgL = (d.fvg || []).map(f => `${f.direction === "bullish" ? "↑" : "↓"} ${_cp(f.bottom)}–${_cp(f.top)} ${f.zone === "discount" ? '<span class="pos">diskon</span>' : f.zone === "premium" ? '<span class="neg">premium</span>' : ""} <span class="muted">${esc(f.state || "")}</span>`);
  const obL = (d.order_blocks || []).filter(_obShow).map(o => `${o.akum ? (o.type === "bull" ? '<span style="color:#66a5f5">⌂ akumulasi</span>' : '<span style="color:#ff9800">⌂ distribusi</span>') : (o.type === "bull" ? '<span style="color:#66a5f5">↑ demand</span>' : '<span style="color:#ff9800">↓ supply</span>')} ${_cp(o.bottom)}–${_cp(o.top)}${o.flip ? ' <span style="color:#c792ea" title="OB demand & supply tumpang-tindih = key level kuat">⇄flip</span>' : ""}${o.vol ? ' <span class="pos" title="volume gerak keluar di atas rata-rata = konfirmasi permintaan/distribusi">✓vol</span>' : ""}${o.retests > 0 ? ` <span class="muted" title="berapa kali di-retest">retest×${o.retests}</span>` : ' <span class="muted">fresh</span>'}`);
  const obSeg = `<span class="ob-seg">${[["all", "Semua"], ["demand", "↑demand"], ["supply", "↓supply"]].map(([f, t]) => `<button type="button" data-obf="${f}" class="${_obFilter === f ? "on" : ""}">${t}</button>`).join("")}</span>`;
  const obRow = `<div class="ind-row"><input type="checkbox" data-ind="ob"${_ind.ob ? " checked" : ""}><span class="ind-sw" style="background:#66a5f5"></span><b class="ind-name">Order Block <span class="muted">(${(d.order_blocks || []).length})</span></b>${obSeg}<span class="ind-detail">${obL.length ? obL.join(" · ") : '<span class="muted">tak terdeteksi</span>'}</span></div>`;
  const fibL = [];
  const _tr = (d.structure || {}).trend;
  const _fdate = s => { try { const dt = new Date(s * 1000); return `${dt.getUTCDate()}/${dt.getUTCMonth() + 1}`; } catch (e) { return ""; } };
  fibL.push(_tr === "range" ? '<span class="neg">⚠ sideways — fib kurang andal</span>' : `tren <b>${esc(_tr || "?")}</b>`);
  if (fib.swing_low && fib.swing_high && fib.swing_low.price != null)   // anchor swing yg DIPAKAI (verifikasi)
    fibL.push(`ditarik: <b>SwL ${_cp(fib.swing_low.price)}</b>${fib.swing_low.time ? ` <span class="muted">${_fdate(fib.swing_low.time)}</span>` : ""} → <b>SwH ${_cp(fib.swing_high.price)}</b>${fib.swing_high.time ? ` <span class="muted">${_fdate(fib.swing_high.time)}</span>` : ""}`);
  if (fib.golden_pocket) fibL.push(`GP ${_cp(Math.min(...fib.golden_pocket))}–${_cp(Math.max(...fib.golden_pocket))}`);
  if (fib.ote) fibL.push(`OTE ${_cp(Math.min(...fib.ote))}–${_cp(Math.max(...fib.ote))}`);
  if (fib.equilibrium != null) fibL.push(`EQ ${_cp(fib.equilibrium)}`);
  const lastSw = (d.swings || []).slice(-1)[0], provKind = lastSw && lastSw.provisional ? lastSw.kind : null;
  const stL = [st.last_swing_high != null ? `SwH ${_cp(st.last_swing_high)}${provKind === "high" ? ' <span class="muted">berjalan</span>' : ""}` : null, st.last_swing_low != null ? `SwL ${_cp(st.last_swing_low)}${provKind === "low" ? ' <span class="muted">berjalan</span>' : ""}` : null, st.event ? esc(String(st.event).toUpperCase()) : null].filter(Boolean);
  const liqL = [];
  (lq.bsl || []).forEach(b => liqL.push(`${b.eq ? '<b style="color:#ff9800">EQH</b>' : "BSL"} ${_cp(b.level)}`));
  (lq.ssl || []).forEach(s => liqL.push(`${s.eq ? '<b style="color:#ff9800">EQL</b>' : "SSL"} ${_cp(s.level)}`));
  if (lq.sweep && lq.sweep.swept) liqL.push(`<span style="color:#ff5252">⚡ sweep ${esc(lq.sweep.type || "")} ${lq.sweep.direction > 0 ? "→ bullish" : "→ bearish"} @ ${_cp(lq.sweep.level)}</span>`);
  const row = (key, color, name, items, note) => {
    const detail = (items && items.length) ? items.join(" · ") : (note || `<span class="muted">tak terdeteksi</span>`);
    return `<label class="ind-row"><input type="checkbox" data-ind="${key}"${_ind[key] ? " checked" : ""}><span class="ind-sw" style="background:${color}"></span><b class="ind-name">${name}</b><span class="ind-detail">${detail}</span></label>`;
  };
  const panel = document.getElementById("chartLegend");
  panel.innerHTML = `<div class="cl-chips">${conf}</div>
    <div class="ind-list">
      ${row("fvg", "#26a69a", `FVG <span class="muted">(${(d.fvg || []).length})</span>`, fvgL)}
      ${row("fib", "#e6b800", "Fibonacci · GP/OTE/EQ", fibL)}
      ${obRow}
      ${row("struct", "#ef5350", "Struktur · Swing H/L", stL)}
      ${row("liq", "#ff9800", "Liquidity · EQH/EQL/Sweep", liqL)}
      ${row("vol", "#8aa0b0", "Volume", null, `<span class="muted">histogram bawah chart</span>`)}
    </div>`;
  panel.querySelectorAll("input[data-ind]").forEach(cb => cb.onchange = () => { _ind[cb.dataset.ind] = cb.checked; _applyOverlays(); });
  panel.querySelectorAll("button[data-obf]").forEach(bt => bt.onclick = () => { _obFilter = bt.dataset.obf; if (!_ind.ob) { _ind.ob = true; } _applyOverlays(); _renderIndicatorPanel(_chartData); });
}
document.querySelectorAll("#tfTabs button").forEach(b => b.onclick = () => { if (_activeSym) renderChart(_activeSym, b.dataset.tf); });

async function analyze(symbol) {
  if (!symbol) return;
  const sym = symbol.trim().toUpperCase();
  _activeSym = sym;
  renderChart(sym, _chartTf);        // chart visual + overlay engine
  const out = document.getElementById("analyzeOut");
  out.innerHTML = `<div class="loading"><div class="spinner"></div> menganalisa ${esc(sym)}…</div>`;
  try {
    const d = await (await fetch(`/api/analyze/${encodeURIComponent(sym)}`)).json();
    let html = `<div class="coin-head" style="margin-top:16px"><span class="coin-sym" style="font-size:22px;font-weight:700">${esc(sym)}</span>
      <span class="muted">bias FVG: ${esc((d.fvg || {}).bias || "?")} · trend: ${esc(((d.structure || {}).structure || {}).trend || "?")}</span></div>`;
    html += `<div class="ac-grid" style="max-width:520px;margin-bottom:14px">
      <div><span>RSI (1h)</span><b>${(d.momentum || {}).rsi != null ? (d.momentum.rsi).toFixed(1) : "—"}</b></div>
      <div><span>Vol state</span><b>${esc((d.momentum || {}).vol_state || "—")}</b></div>
      <div><span>FR score</span><b>${(d.sentiment || {}).fr_score ?? "—"}</b></div>
      <div><span>LSR score</span><b>${(d.sentiment || {}).lsr_score ?? "—"}</b></div>
    </div>`;
    html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">${_confluenceSection("Scalp (5m)", d.scalp)}${_confluenceSection("Swing (4h)", d.swing)}</div>`;
    html += `<div id="narrativeBox" class="narrative"><div class="narr-head"><span class="narr-av">◈</span> <b>Analisa &amp; kesimpulan</b> <span class="muted">— Vega + LLM · multi-timeframe</span></div>
      <div id="narrativeBody" class="narr-body"><div class="loading"><div class="spinner"></div> agent menyusun analisa…</div></div></div>`;
    out.innerHTML = html;
    _loadNarrative(sym, _chartTf);      // narasi + kesimpulan agent (async, tak blok chart)
  } catch (e) {
    out.innerHTML = `<p class="muted">gagal memuat analisa: ${esc(String(e))}</p>`;
  }
}
function _mtfTable(mtf) {
  if (!mtf || !mtf.length) return "";
  const trCls = t => t === "uptrend" ? "pos" : t === "downtrend" ? "neg" : "";
  const row = r => r.error
    ? `<tr><td><b>${esc(r.tf)}</b></td><td colspan="5" class="muted">${esc(r.error)}</td></tr>`
    : `<tr><td><b>${esc(r.tf)}</b></td>
        <td><b class="${trCls(r.trend)}">${esc(r.trend || "?")}</b></td>
        <td class="r"><b class="${r.score_teknikal > 0 ? "pos" : r.score_teknikal < 0 ? "neg" : ""}">${r.score_teknikal > 0 ? "+" : ""}${r.score_teknikal ?? "?"}</b></td>
        <td>${esc(r.zona || "?")}</td>
        <td>${esc(r.fib || "?")}${r.di_GP ? ' <span class="pos">·GP</span>' : r.di_OTE ? ' <span class="pos">·OTE</span>' : ""}</td>
        <td class="r">${r.rsi ?? "—"} <span class="muted">${esc(r.vol_state || "")}</span></td></tr>`;
  return `<div class="mtf-head muted">Data multi-timeframe (top-down):</div>
    <div class="dtable-wrap" style="margin:4px 0 12px"><table class="dtable"><thead>
    <tr><th>TF</th><th>Tren</th><th class="r">Skor</th><th>Zona</th><th>Fib</th><th class="r">RSI/vol</th></tr>
    </thead><tbody>${mtf.map(row).join("")}</tbody></table></div>`;
}
async function _loadNarrative(sym, tf) {
  const body = document.getElementById("narrativeBody");
  if (!body) return;
  try {
    const d = await (await fetch(`/api/narrative/${encodeURIComponent(sym)}?tf=${tf}`)).json();
    if (d.ok && d.narrative) body.innerHTML = _mtfTable(d.mtf) + md(d.narrative);
    else body.innerHTML = _mtfTable(d.mtf) + `<p class="muted">Narasi LLM tak tersedia saat ini (${esc(d.error || "—")}). Data MTF & confluence di atas tetap valid.</p>`;
  } catch (e) {
    body.innerHTML = `<p class="muted">gagal memuat narasi: ${esc(String(e))}</p>`;
  }
}

// ── Sinyal ────────────────────────────────────────────
async function loadSignals() {
  const out = document.getElementById("signalsOut");
  out.innerHTML = `<div class="loading"><div class="spinner"></div> memuat sinyal…</div>`;
  const onlyStrong = document.getElementById("sigOnlyStrong").checked;
  try {
    const d = await (await fetch(`/api/signals?full_strong_only=${onlyStrong}`)).json();
    const rows = d.signals || [];
    document.getElementById("signalsMeta").textContent = rows.length ? `${rows.length} sinyal` : "";
    if (!rows.length) { out.innerHTML = `<p class="muted">Belum ada sinyal — menunggu siklus scan berikutnya.</p>`; return; }
    const thead = `<tr><th>Koin</th><th>Gaya</th><th class="r">Score</th><th>Zona</th><th>Arah</th><th class="r">Entry</th><th class="r">SL</th><th>Alasan</th></tr>`;
    const rowFn = r => `<tr>
      <td><b>${esc(r.symbol)}</b></td><td class="muted">${esc(r.group)}</td>
      <td class="r"><b class="${r.full_score > 0 ? "pos" : r.full_score < 0 ? "neg" : ""}">${r.full_score > 0 ? "+" : ""}${r.full_score}</b></td>
      <td>${zoneChip(r.zone)}</td><td>${r.direction === 1 ? '<span class="pos">LONG</span>' : r.direction === -1 ? '<span class="neg">SHORT</span>' : "—"}</td>
      <td class="r">${fmtPrice(r.entry)}</td><td class="r">${fmtPrice(r.sl)}</td>
      <td class="muted">${esc(r.reason || (r.full_strong ? "lolos gerbang" : ""))}</td></tr>`;
    out.innerHTML = pagedTable("sig", "Sinyal terbaru", thead, rows, rowFn, { open: true });
  } catch (e) {
    out.innerHTML = `<p class="muted">gagal memuat: ${esc(String(e))}</p>`;
  }
}
document.getElementById("sigOnlyStrong").onchange = loadSignals;

// ── Universe ──────────────────────────────────────────
let _uniRows = [];
async function loadUniverse() {
  const out = document.getElementById("universeOut");
  out.innerHTML = `<div class="loading"><div class="spinner"></div> memuat universe…</div>`;
  try {
    const d = await (await fetch("/api/universe")).json();
    _uniRows = d.tokens || [];
    renderUniverse();
  } catch (e) {
    out.innerHTML = `<p class="muted">gagal memuat: ${esc(String(e))}</p>`;
  }
}
function renderUniverse() {
  const out = document.getElementById("universeOut");
  const q = (document.getElementById("uniSearch").value || "").toUpperCase();
  const rows = _uniRows.filter(r => !q || r.symbol.includes(q) || (r.name || "").toUpperCase().includes(q));
  if (!rows.length) { out.innerHTML = `<p class="muted">Belum ada data universe — jalankan refresh (chat: "refresh universe").</p>`; return; }
  const thead = `<tr><th>Koin</th><th>Tier Scalp</th><th>Tier Swing</th><th class="r">Mcap</th><th class="r">Volume 24h</th><th class="r">24 jam</th></tr>`;
  const badge = t => `<span class="tier-badge ${esc(t || "")}">${esc(t || "—")}</span>`;
  const chg = v => v == null ? `<span class="muted">—</span>` : `<span class="${v >= 0 ? "pos" : "neg"}">${v >= 0 ? "+" : ""}${v.toFixed(2)}%</span>`;
  const rowFn = r => `<tr><td><b>${esc(r.symbol)}</b> <span class="muted">${esc(r.name || "")}</span></td>
    <td>${badge(r.scalp_tier)}</td><td>${badge(r.swing_tier)}</td>
    <td class="r">$${fmtUsd(r.market_cap)}</td><td class="r">$${fmtUsd(r.volume_24h)}</td>
    <td class="r">${chg(r.percent_change_24h)}</td></tr>`;
  out.innerHTML = pagedTable("uni", "Universe", thead, rows, rowFn, { open: true, per: 20 });
}
document.getElementById("uniSearch").oninput = renderUniverse;

// ── Agent (dry-run dashboard) ───────────────────────────
function _tpLadder(tps, fills) {
  const filledLabels = new Set((fills || []).map(f => f.label));
  return `<div class="tp-ladder">${(tps || []).map(t => {
    const isFilled = filledLabels.has(t.label);
    const isSl = filledLabels.has("SL") && t.label === "SL";
    return `<div class="tp-step ${isFilled ? "filled" : ""} ${isSl ? "sl-hit" : ""}" title="${t.label}"></div>`;
  }).join("")}</div><div class="tp-labels">${(tps || []).map(t => `<span>${t.label}</span>`).join("")}</div>`;
}
function _posCard(p) {
  const pnlCls = (p.realized_pnl_usd || 0) >= 0 ? "pos" : "neg";
  return `<div class="pos-card">
    <div class="pos-head"><span class="pos-sym">${legTag(p.leg)} - ${esc(p.symbol)} <span class="muted">${esc(p.group)} · ${p.leverage}x</span></span>
      <b class="${pnlCls}">${p.realized_pnl_usd >= 0 ? "+" : ""}$${(p.realized_pnl_usd || 0).toFixed(2)}${p.r_multiple != null ? ` (${p.r_multiple > 0 ? "+" : ""}${p.r_multiple}R)` : ""}</b></div>
    <div class="ac-grid"><div><span>Entry</span><b>${fmtPrice(p.entry)}</b></div><div><span>SL</span><b>${fmtPrice(p.sl)}</b></div>
      <div><span>Qty sisa</span><b>${fmtQty(p.qty_remaining)} / ${fmtQty(p.original_qty)}</b></div><div><span>Score</span><b>${p.full_score}</b></div></div>
    <div class="ac-grid" style="margin-top:6px">
      <div><span>Harga terkini</span><b>${p.current_price != null ? fmtPrice(p.current_price) : "—"}${p.price_move_pct != null ? ` <span class="${p.price_move_pct >= 0 ? "pos" : "neg"}" style="font-size:11px">(${p.price_move_pct >= 0 ? "+" : ""}${p.price_move_pct}%)</span>` : ""}</b></div>
      <div><span>PnL berjalan (unreal.)</span><b class="${(p.unrealized_pnl_usd || 0) >= 0 ? "pos" : "neg"}">${p.unrealized_pnl_usd != null ? `${p.unrealized_pnl_usd >= 0 ? "+" : ""}$${p.unrealized_pnl_usd.toFixed(2)}${p.unrealized_pct != null ? ` (${p.unrealized_pct >= 0 ? "+" : ""}${p.unrealized_pct}%)` : ""}` : "—"}</b></div>
      <div><span>Margin (dari equity)</span><b>$${(p.margin_usd || 0).toFixed(2)}${p.margin_pct != null ? ` · ${p.margin_pct}%` : ""}</b></div>
      <div><span>Notional (×${p.leverage})</span><b>$${(p.notional_usd || 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}${p.notional_pct != null ? ` · ${p.notional_pct}%` : ""}</b></div>
      <div><span>Funding rate (8j)</span><b>${p.funding_rate != null ? (p.funding_rate * 100).toFixed(4) + "%" : "—"}</b></div>
      <div><span>Funding fee</span><b class="${(p.funding_paid_usd || 0) >= 0 ? "pos" : "neg"}">${(p.funding_paid_usd || 0) >= 0 ? "+" : ""}$${(p.funding_paid_usd || 0).toFixed(4)}</b></div></div>
    ${_tpLadder(p.tps, p.fills)}
    ${_tpPrices(p)}
  </div>`;
}
function _tpPrices(p) {
  if (!p.tps || !p.tps.length) return "";
  const filled = new Set((p.fills || []).map(f => f.label));
  const dir = p.leg === "long" ? 1 : -1;
  const rows = p.tps.map(t => {
    const done = filled.has(t.label);
    const mv = (t.price != null && p.entry) ? ((t.price - p.entry) / p.entry * dir * 100) : null;
    return `<div class="tpp-row${done ? " done" : ""}"><span>${done ? "✓" : "◦"} ${esc(t.label)} · ${(t.frac * 100).toFixed(0)}%</span>
      <b>${t.price != null ? fmtPrice(t.price) : "—"}${mv != null ? ` <span class="muted" style="font-weight:400">(+${mv.toFixed(1)}%)</span>` : ""}</b></div>`;
  }).join("");
  return `<div class="tpp"><div class="tpp-row hdr"><span>Entry ${fmtPrice(p.entry)}</span><b>SL ${fmtPrice(p.sl)}</b></div>${rows}</div>`;
}
function _pendingCard(p) {
  const dir = legTag(p.leg);
  return `<div class="pos-card pending">
    <div class="pos-head"><span class="pos-sym">${dir} - ${esc(p.symbol)} <span class="muted">${esc(p.group)} · ${p.leverage}x</span></span>
      <span class="pending-badge">◷ LIMIT menunggu</span></div>
    <div class="ac-grid"><div><span>Limit</span><b>${fmtPrice(p.entry)}</b></div>
      <div><span>Harga terkini</span><b>${p.current_price != null ? fmtPrice(p.current_price) : (p.mark_price != null ? fmtPrice(p.mark_price) : "—")}${p.current_price != null && p.entry ? ` <span class="muted" style="font-size:11px">(${(Math.abs(p.current_price - p.entry) / p.entry * 100).toFixed(2)}% ke limit)</span>` : ""}</b></div>
      <div><span>SL</span><b>${fmtPrice(p.sl)}</b></div><div><span>Score</span><b>${p.full_score}</b></div></div>
    <div class="ac-grid" style="margin-top:6px">
      <div><span>Qty</span><b>${fmtQty(p.original_qty)}</b></div>
      <div><span>Margin (dari equity)</span><b>$${(p.margin_usd || 0).toFixed(2)}${p.margin_pct != null ? ` · ${p.margin_pct}%` : ""}</b></div>
      <div><span>Notional (×${p.leverage})</span><b>$${(p.notional_usd || 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}</b></div>
      <div><span>Funding rate (8j)</span><b>${p.funding_rate != null ? (p.funding_rate * 100).toFixed(4) + "%" : "—"}</b></div></div>
    <div class="tp-labels" style="margin-top:6px"><span>Dipasang ${p.placed_ts ? new Date(p.placed_ts).toLocaleString() : ""}</span></div>
  </div>`;
}
async function loadAgent(silent) {
  const out = document.getElementById("agentOut"), summ = document.getElementById("agentSummary");
  if (!silent) out.innerHTML = `<div class="loading"><div class="spinner"></div> memuat…</div>`;
  try {
    const d = await (await fetch("/api/agent")).json();
    summ.innerHTML = `<div class="agent-cards">${(d.summary || []).map(s => `
      <div class="agent-card"><div class="grp-h">${esc(s.group)}</div>
        <div class="ac-big">$${s.equity.toFixed(2)}</div>
        <div class="roi-row">
          <div class="roi-box"><span>ROI total<small>(+ posisi terbuka)</small></span><b class="${(s.roi_total_pct ?? s.return_pct) >= 0 ? "pos" : "neg"}">${(s.roi_total_pct ?? s.return_pct) >= 0 ? "+" : ""}${s.roi_total_pct ?? s.return_pct}%</b></div>
          <div class="roi-box"><span>ROI realized<small>(trade tutup)</small></span><b class="${s.return_pct >= 0 ? "pos" : "neg"}">${s.return_pct >= 0 ? "+" : ""}${s.return_pct}%</b></div>
        </div>
        <div class="ac-grid"><div><span>Open</span><b>${s.open}</b></div><div><span>Closed</span><b>${s.closed}</b></div>
          <div><span>Win-rate</span><b>${s.win_rate != null ? s.win_rate + "%" : "—"}</b></div>
          <div><span>Unreal. PnL</span><b class="${(s.unrealized_pnl_usd || 0) >= 0 ? "pos" : "neg"}">${(s.unrealized_pnl_usd || 0) >= 0 ? "+" : ""}$${(s.unrealized_pnl_usd || 0).toFixed(2)}</b></div>
          <div><span>Leverage</span><b>${esc(s.leverage_range)}</b></div>
          <div><span>Max posisi</span><b>${s.max_open}</b></div></div>
        <div class="ac-expectancy">Expectancy: <b>${s.expectancy_r != null ? (s.expectancy_r > 0 ? "+" : "") + s.expectancy_r + "R" : "belum cukup sampel"}</b> <span class="muted">— ukuran utama, bukan win-rate</span></div>
      </div>`).join("")}</div>`;
    let html = "";
    // LIMIT order menunggu — bisa minimize/maximize (collapsible), 5/halaman
    if (d.pending && d.pending.length) html += pagedCards("pending", "LIMIT order menunggu", d.pending, _pendingCard, { per: 5, collapsible: true, open: true });
    // Posisi terbuka — DIPISAH scalp/swing, SELALU tampil (tak collapsible), 5/halaman
    const openS = (d.open || []).filter(p => p.group === "scalp");
    const openW = (d.open || []).filter(p => p.group === "swing");
    if (openS.length) html += pagedCards("openS", "Posisi terbuka · Scalp", openS, _posCard, { per: 5 });
    if (openW.length) html += pagedCards("openW", "Posisi terbuka · Swing", openW, _posCard, { per: 5 });
    if (!openS.length && !openW.length && !(d.pending && d.pending.length)) html += `<p class="muted">Tidak ada posisi terbuka atau limit order menunggu.</p>`;
    if (d.closed && d.closed.length) {
      const _hold = (a, b) => { if (!a || !b) return "—"; const h = (new Date(b) - new Date(a)) / 3.6e6; return h < 24 ? h.toFixed(1) + " jam" : (h / 24).toFixed(1) + " hari"; };
      const thead = `<tr><th>Koin</th><th>Lev</th><th class="r">Entry</th><th class="r">Exit (di mana)</th><th class="r">PnL</th><th class="r">R</th><th>Hasil</th><th class="r">Funding</th><th>Durasi</th></tr>`;
      const rowFn = r => {
        const fills = r.fills || [], last = fills[fills.length - 1];
        const exitStr = last ? `${esc(last.label)} @ ${fmtPrice(last.price)}` : "—";
        const ocBadge = r.outcome === "tp_full" ? '<span class="pos">TP</span>' : r.outcome === "sl" ? '<span class="neg">SL</span>' : `<span class="muted">${esc(r.outcome || "—")}</span>`;
        const fillsStr = fills.length ? fills.map(f => `${esc(f.label)} ${r.original_qty ? (f.qty / r.original_qty * 100).toFixed(0) + "%" : ""} @ ${fmtPrice(f.price)} (${f.pnl_usd >= 0 ? "+" : ""}$${(f.pnl_usd || 0).toFixed(2)})`).join(" · ") : "—";
        return `<tr class="ct-sum">
          <td>${legTag(r.leg)} - <b>${esc(r.symbol)}</b> <span class="muted">${esc(r.group)}</span></td>
          <td class="muted">${r.leverage}x</td>
          <td class="r">${fmtPrice(r.entry)}</td>
          <td class="r">${exitStr}</td>
          <td class="r ${(r.realized_pnl_usd || 0) >= 0 ? "pos" : "neg"}">${(r.realized_pnl_usd || 0) >= 0 ? "+" : ""}$${(r.realized_pnl_usd || 0).toFixed(2)}</td>
          <td class="r ${(r.r_multiple || 0) >= 0 ? "pos" : "neg"}">${r.r_multiple != null ? (r.r_multiple >= 0 ? "+" : "") + r.r_multiple + "R" : "—"}</td>
          <td>${ocBadge}</td>
          <td class="r ${(r.funding_paid_usd || 0) >= 0 ? "pos" : "neg"}">${(r.funding_paid_usd || 0) >= 0 ? "+" : ""}$${(r.funding_paid_usd || 0).toFixed(4)}</td>
          <td class="muted">${_hold(r.entry_ts, r.closed_at)}</td></tr>
        <tr class="ct-det"><td colspan="9"><span class="muted">SL awal ${fmtPrice(r.sl)} · rincian fill: ${fillsStr} · funding ${(r.funding_paid_usd || 0) >= 0 ? "+" : ""}$${(r.funding_paid_usd || 0).toFixed(4)} · ditutup ${r.closed_at ? new Date(r.closed_at).toLocaleString() : ""}</span></td></tr>`;
      };
      html += pagedTable("closed", "Riwayat tertutup (detail simulasi & evaluasi)", thead, d.closed, rowFn, { per: 10 });
    }
    out.innerHTML = html;
  } catch (e) {
    if (!silent) out.innerHTML = `<p class="muted">gagal memuat: ${esc(String(e))}</p>`;
  }
}
(() => {
  document.getElementById("agentRefresh").onclick = () => loadAgent();
  const lb = document.getElementById("agentLive");
  lb.onclick = () => { _agentLive = !_agentLive; lb.classList.toggle("on", _agentLive); lb.textContent = _agentLive ? "● Live" : "○ Live"; if (_agentLive) { startAgentPoll(); loadAgent(true); } else stopAgentPoll(); };
  document.getElementById("agentStep").onclick = async () => {
    const b = document.getElementById("agentStep"); b.disabled = true; const old = b.textContent; b.textContent = "⚡ berjalan…";
    try { await fetch("/api/agent/step", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); } catch {}
    b.disabled = false; b.textContent = old; loadAgent();
  };
  document.getElementById("agentReset").onclick = async () => {
    const word = await confirmAction({
      title: "⚠ Reset TOTAL dry-run", word: "RESET", btnLabel: "Reset sekarang", danger: true,
      body: `<p class="modal-p">Menghapus <b>SEMUA</b> data dry-run (kedua gaya): posisi, riwayat, PnL — mulai dari nol. <b>Tidak bisa dibatalkan.</b></p>`,
    });
    if (!word) return;
    try {
      const r = await fetch("/api/agent/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: word }) });
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert(d.detail || "gagal reset."); return; }
      loadAgent();
    } catch { alert("gagal menghubungi server."); }
  };
})();

// ── Admin ─────────────────────────────────────────────
let _adminToken = localStorage.getItem("smc_admin_token") || "";
async function initAdmin() {
  const out = document.getElementById("adminOut");
  out.innerHTML = `<div class="field"><label>🔑 Password Admin</label>
      <div style="display:flex;gap:8px;align-items:stretch">
        <input id="admToken" type="password" value="${esc(_adminToken)}" placeholder="masukkan ADMIN_TOKEN" style="flex:1" autocomplete="current-password">
        <button id="admLogin" class="save-btn" style="white-space:nowrap;margin:0">Masuk →</button>
      </div></div>
    <p class="muted" style="font-size:12px;margin:-4px 0 14px">Password admin = <code>ADMIN_TOKEN</code>. Pertama kali: set di file <code>.env</code> runtime (<code>ADMIN_TOKEN=…</code>) lalu restart. Setelah itu bisa diganti dari panel ini (bagian Rahasia).</p>
    <div id="admBody"><p class="muted">Masukkan password admin lalu tekan <b>Masuk</b> (atau Enter) untuk mengelola mode otoritas agent, LLM, & kunci.</p></div>`;
  const unlock = () => { _adminToken = document.getElementById("admToken").value.trim(); localStorage.setItem("smc_admin_token", _adminToken);
    document.getElementById("admBody").innerHTML = `<p class="muted">memuat…</p>`; loadAdminConfig(); };
  document.getElementById("admLogin").onclick = unlock;
  document.getElementById("admToken").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); unlock(); } };
  document.getElementById("admToken").onchange = unlock;
  if (_adminToken) loadAdminConfig();
}
const _AUTH_META = {
  none:   { icon: "🔒", label: "Tanpa Otoritas", tag: "default · paling aman",
            desc: "Agent hanya OBSERVASI & ANALISA (FVG/struktur/sentimen/sinyal/status). Tidak bisa ubah config, tidak bisa edit kode, tidak bisa jalankan operasi." },
  medium: { icon: "⚙️", label: "Menengah", tag: "config saja",
            desc: "Agent bisa setel PARAMETER metodologi (gerbang, filter, leverage, dll) + operasi dry-run. TIDAK bisa edit kode." },
  full:   { icon: "🔓", label: "Penuh", tag: "config + KODE · hati-hati",
            desc: "Agent bisa edit KODE (write_source/run_tests, berlaku live) + parameter + operasi. Risiko RCE bila web terekspos publik — jaga localhost + tanpa kunci exchange withdraw." },
};
async function _fetchModels() {
  try { const r = await fetch("/api/admin/models", { headers: { "X-Admin-Token": _adminToken } }); const d = await r.json(); return d.models || []; }
  catch { return []; }
}
async function loadAdminConfig() {
  const body = document.getElementById("admBody");
  try {
    const r = await fetch("/api/admin/config", { headers: { "X-Admin-Token": _adminToken } });
    if (!r.ok) { body.innerHTML = `<p class="muted">${r.status === 401 ? "Token salah." : "Admin nonaktif — set <code>ADMIN_TOKEN</code> di file <code>.env</code> lalu restart."}</p>`; return; }
    const cfg = await r.json();
    const models = await _fetchModels();
    const cur = cfg.agent_authority || "none";
    const levels = cfg._authority_levels || ["none", "medium", "full"];

    // 1) Mode otoritas agent — kartu radio
    const authCards = levels.map(lv => { const m = _AUTH_META[lv] || { icon: "?", label: lv, tag: "", desc: "" };
      return `<label class="auth-card ${cur === lv ? "sel" : ""}">
        <input type="radio" name="authmode" value="${lv}" ${cur === lv ? "checked" : ""}>
        <div class="auth-h"><span class="auth-ic">${m.icon}</span><b>${m.label}</b><span class="auth-tag">${m.tag}</span></div>
        <div class="auth-d">${esc(m.desc)}</div></label>`; }).join("");

    // 2) LLM — base URL (teks) + model orch/light (dropdown bila ada daftar model)
    const modelSel = (k, v) => models.length
      ? `<select data-k="${k}">${models.map(m => `<option ${m === v ? "selected" : ""}>${esc(m)}</option>`).join("")}${models.includes(v) ? "" : `<option selected>${esc(v || "")}</option>`}</select>`
      : `<input data-k="${k}" value="${esc(v || "")}" placeholder="nama model">`;

    // 3) Rahasia (password + badge set/unset)
    const secretField = (k) => { const o = cfg[k] || {}; return `<div class="field"><label>${esc(k)} ${o.set ? `<span class="badge-set">✓ terpasang ${esc(o.hint)}</span>` : `<span class="badge-unset">belum diset</span>`}</label>
      <input data-k="${k}" type="password" autocomplete="new-password" placeholder="${o.set ? "isi utk ganti…" : "isi kunci…"}"></div>`; };

    body.innerHTML = `
      <div class="adm-sec"><h3 class="adm-h">🤖 Mode Otoritas Agent</h3>
        <p class="muted" style="margin:2px 0 10px">Menentukan seberapa jauh agent (Orin) boleh mengubah sistem. Berlaku langsung.</p>
        <div class="auth-grid">${authCards}</div></div>
      <div class="adm-sec"><h3 class="adm-h">🧠 LLM</h3>
        <div class="field"><label>LLM_BASE_URL</label><input data-k="LLM_BASE_URL" value="${esc(cfg.LLM_BASE_URL || "")}" placeholder="http://…/v1"></div>
        <div class="field"><label>Model Orchestrator</label>${modelSel("LLM_MODEL_ORCH", cfg.LLM_MODEL_ORCH)}</div>
        <div class="field"><label>Model Ringan</label>${modelSel("LLM_MODEL_LIGHT", cfg.LLM_MODEL_LIGHT)}</div></div>
      <div class="adm-sec"><h3 class="adm-h">🔑 Rahasia / Kunci</h3>
        ${secretField("ADMIN_TOKEN")}${secretField("CMC_API_KEY")}${secretField("TELEGRAM_BOT_TOKEN")}
        <div class="field"><label>TELEGRAM_ALLOWED_CHAT_IDS</label><input data-k="TELEGRAM_ALLOWED_CHAT_IDS" value="${esc(cfg.TELEGRAM_ALLOWED_CHAT_IDS || "")}" placeholder="123,456"></div></div>
      <button class="save-btn" id="admSave">Simpan perubahan</button><span id="adminMsg"></span>`;

    body.querySelectorAll(".auth-card input").forEach(i => i.onchange = () => {
      body.querySelectorAll(".auth-card").forEach(c => c.classList.toggle("sel", c.querySelector("input").checked));
    });
    document.getElementById("admSave").onclick = async () => {
      const payload = {};
      const am = body.querySelector("input[name=authmode]:checked"); if (am) payload.agent_authority = am.value;
      body.querySelectorAll("[data-k]").forEach(i => { const val = (i.value || "").trim(); if (val) payload[i.dataset.k] = val; });
      const r2 = await fetch("/api/admin/config", { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Token": _adminToken }, body: JSON.stringify(payload) });
      const d2 = await r2.json();
      const msg = document.getElementById("adminMsg");
      msg.textContent = r2.ok ? `✓ tersimpan: ${(d2.updated || []).join(", ") || "(tak ada perubahan)"}` : (d2.detail || "gagal");
      msg.className = r2.ok ? "pos" : "neg";
      if (r2.ok) setTimeout(loadAdminConfig, 600);
    };
  } catch (e) { body.innerHTML = `<p class="muted">gagal memuat: ${esc(String(e))}</p>`; }
}

// ── Chat mengambang dengan Orchestrator (Orin) — sadar konteks + histori sesi ──
const _chat = { history: [], busy: false, sid: null, status: null, unread: 0 };
const CHAT_GREET = "Selamat datang. Saya **Orin**, orchestrator sistem ini. Saya memahami halaman yang sedang Anda buka dan data terkini di dalamnya. Silakan bertanya soal confluence, sinyal, atau status dry-run.";
function _toolLabel(name) {
  const M = {
    fvg_analyze: "◭ baca FVG", structure_analyze: "◭ baca struktur/Fib/OB", sentiment_analyze: "◵ cek sentimen derivatif",
    momentum_analyze: "◵ cek momentum", confluence_signal: "◆ hitung sinyal confluence", dryrun_summary: "⌁ rekap dry-run",
    dryrun_positions: "⌁ cek posisi terbuka", tier_list: "▤ baca universe", screening_highlights: "◆ scan sinyal terbaru",
    db_query: "▤ query data", read_file: "▤ baca file", list_dir: "▤ list direktori",
    rnd_step: "⌁ jalankan siklus dry-run", rnd_universe_refresh: "▤ refresh universe",
  };
  return M[name] || ("◆ pakai " + name);
}
function _chatLight(state) {
  const d = document.querySelector(".chat-dot"); if (!d) return;
  d.classList.remove("busy", "error");
  if (state === "busy") d.classList.add("busy");
  else if (state === "error") d.classList.add("error");
}
function _chatVisible() {
  const p = document.getElementById("chatPanel");
  return p && p.classList.contains("open") && !p.classList.contains("minimized");
}
function _chatMarkUnread() {
  if (_chatVisible()) return;
  _chat.unread++;
  const fab = document.getElementById("chatFab"); if (fab) fab.classList.add("unread");
  const b = document.getElementById("chatUnread"); if (b) { b.hidden = false; b.textContent = _chat.unread + " baru"; }
}
function _chatClearUnread() {
  _chat.unread = 0;
  const fab = document.getElementById("chatFab"); if (fab) fab.classList.remove("unread");
  const b = document.getElementById("chatUnread"); if (b) b.hidden = true;
}
let _sessions = [];
function _relTime(ts) {
  if (!ts) return ""; const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return "baru saja"; if (s < 3600) return Math.floor(s / 60) + "m lalu";
  if (s < 86400) return Math.floor(s / 3600) + "j lalu"; return Math.floor(s / 86400) + "h lalu";
}
async function _persistSession() {
  if (!_chat.sid || !_chat.history.some(m => m.role === "user")) return;
  try {
    await fetch("/api/chat/sessions/" + encodeURIComponent(_chat.sid), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: _chat.history }),
    });
  } catch {}
}
function _newSession() { _chat.sid = "s" + Date.now(); _chat.history = [{ role: "assistant", content: CHAT_GREET }]; _toggleSessions(false); _chatRender(); }
async function _resumeSession(id) {
  try {
    const r = await fetch("/api/chat/sessions/" + encodeURIComponent(id));
    if (!r.ok) return;
    const d = await r.json();
    _chat.sid = id; _chat.history = (d.messages || []).slice(); _toggleSessions(false); _chatRender();
  } catch {}
}
function _chatCtx() {
  const t = document.querySelector(".tab.is-active");
  const sym = _activeSym || "";
  return { tab: (t && t.dataset.tab) || "analyze", symbol: sym };
}
function _chatRender() {
  const body = document.getElementById("chatBody");
  if (!body) return;
  if (!_chat.history.length && !_chat.busy) {
    body.innerHTML = `<div class="chat-empty muted">Obrolan kosong — ketik sesuatu untuk mulai berdiskusi dengan Orin.</div>`;
  } else {
    body.innerHTML = _chat.history.map(m =>
      `<div class="cmsg ${m.role}">${m.role === "user" ? esc(m.content) : md(m.content)}</div>`).join("")
      + (_chat.busy ? `<div class="cmsg assistant working"><span class="spinner small"></span> ${esc(_chat.status || "Orin sedang bekerja…")}</div>` : "");
  }
  body.scrollTop = body.scrollHeight;
  const c = _chatCtx(), ce = document.getElementById("chatCtx");
  if (ce) ce.textContent = `konteks: tab ${c.tab}${c.symbol ? " · " + c.symbol : ""}`;
  if (_chat.unread && _chatVisible()) _chatClearUnread();
}
async function _renderSessions() {
  const el = document.getElementById("chatSessions"); if (!el) return;
  el.innerHTML = `<div class="sess-head"><b>Histori sesi</b> <span class="muted" style="font-size:10px">(memori agent)</span><button id="sessNew" class="ctab">✚ Sesi baru</button></div><div class="sess-list"><div class="muted" style="padding:18px;text-align:center"><span class="spinner small"></span> memuat…</div></div>`;
  document.getElementById("sessNew").onclick = _newSession;
  try { _sessions = await (await fetch("/api/chat/sessions")).json(); } catch { _sessions = []; }
  const items = (_sessions && _sessions.length) ? _sessions.map(s => `
    <div class="sess-item ${s.id === _chat.sid ? "cur" : ""}" data-id="${s.id}">
      <div class="sess-main"><div class="sess-title">${esc(s.title || "Sesi")}</div>
        <div class="sess-time muted">${_relTime(s.updated)} · ${s.n || 0} pesan</div></div>
      <button class="sess-del icon-btn" data-del="${s.id}" title="hapus sesi">✕</button>
    </div>`).join("") : `<div class="muted" style="padding:24px;text-align:center">Belum ada sesi tersimpan.</div>`;
  const list = el.querySelector(".sess-list"); if (list) list.innerHTML = items;
  el.querySelectorAll(".sess-item").forEach(it => it.onclick = (e) => { if (!e.target.closest("[data-del]")) _resumeSession(it.dataset.id); });
  el.querySelectorAll("[data-del]").forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    try { await fetch("/api/chat/sessions/" + encodeURIComponent(b.dataset.del), { method: "DELETE" }); } catch {}
    if (_chat.sid === b.dataset.del) { _chat.sid = null; _chat.history = []; }
    _renderSessions(); _chatRender();
  });
}
function _toggleSessions(show) {
  const el = document.getElementById("chatSessions"); if (!el) return;
  if (show === undefined) show = !el.classList.contains("open");
  el.classList.toggle("open", show);
  if (show) _renderSessions();
}
async function _chatSend(text) {
  text = (text || "").trim();
  if (!text || _chat.busy) return;
  if (!_chat.sid) _chat.sid = "s" + Date.now();
  _chat.history.push({ role: "user", content: text });
  _chat.busy = true; _chat.status = "Orin sedang meninjau…"; _chatLight("busy"); _chatRender();
  _chat.abort = new AbortController();
  let reply = null, err = false, stopped = false;
  try {
    const r = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: _chat.history.slice(-8), context: _chatCtx() }),
      signal: _chat.abort.signal,
    });
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 2);
        if (!line.startsWith("data:")) continue;
        let ev; try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
        if (ev.type === "tool") _chat.status = _toolLabel(ev.name) + "…";
        else if (ev.type === "final") reply = ev.reply;
        else if (ev.type === "error") { err = true; reply = "Ada kendala: " + (ev.error || "tak jelas") + "."; }
        _chatRender();
      }
    }
  } catch (e) {
    if (e && e.name === "AbortError") stopped = true;
    else { err = true; reply = "Gagal terhubung. Coba lagi sebentar."; }
  }
  _chat.abort = null;
  if (!stopped) _chat.history.push({ role: "assistant", content: reply || "(maaf, tak ada jawaban — coba ulangi)" });
  _chat.busy = false; _chat.status = null;
  _chatLight(err ? "error" : "idle");
  _chatRender();
  if (!stopped) { _persistSession(); _chatMarkUnread(); }
}
const CHAT_CMDS = {
  "/retry": "ulangi — kirim ulang pesan terakhir Anda untuk jawaban baru",
  "/continue": "lanjutkan / perdalam jawaban Orin yang terakhir",
  "/stop": "hentikan proses yang sedang berjalan",
  "/clear": "HAPUS obrolan ini dari memori agent (permanen)",
  "/help": "tampilkan daftar command",
};
function _chatHelp() {
  return "**Command yang tersedia:**\n" + Object.entries(CHAT_CMDS).map(([k, v]) => `- \`${k}\` — ${v}`).join("\n");
}
function _chatRetry() {
  if (_chat.busy) return;
  while (_chat.history.length && _chat.history[_chat.history.length - 1].role === "assistant") _chat.history.pop();
  const last = _chat.history[_chat.history.length - 1];
  if (!last || last.role !== "user") { _chat.history.push({ role: "assistant", content: "Tidak ada pesan untuk di-retry." }); _chatRender(); return; }
  const text = last.content; _chat.history.pop(); _chatSend(text);
}
async function _chatRunCommand(raw) {
  const cmd = raw.split(/\s+/)[0].toLowerCase();
  switch (cmd) {
    case "/help": _chat.history.push({ role: "assistant", content: _chatHelp() }); _chatRender(); break;
    case "/retry": _chatRetry(); break;
    case "/continue": _chatSend("Lanjutkan / perdalam jawaban Anda barusan — jangan mengulang dari awal."); break;
    case "/stop": if (_chat.abort) _chat.abort.abort(); break;
    case "/clear":
      if (_chat.sid) { try { await fetch("/api/chat/sessions/" + encodeURIComponent(_chat.sid), { method: "DELETE" }); } catch {} }
      _chat.sid = null; _chat.history.length = 0; _chatRender();
      break;
    default: _chat.history.push({ role: "assistant", content: `Command \`${esc(cmd)}\` tak dikenal. Ketik \`/help\` untuk daftar.` }); _chatRender();
  }
}
function _chatCmdSuggest(val) {
  const el = document.getElementById("chatCmdHint"); if (!el) return;
  if (!val.startsWith("/") || val.includes(" ")) { el.hidden = true; return; }
  const q = val.toLowerCase(), matches = Object.entries(CHAT_CMDS).filter(([k]) => k.startsWith(q));
  if (!matches.length) { el.hidden = true; return; }
  el.innerHTML = matches.map(([k, v]) => `<div class="cmd-row" data-cmd="${k}"><code>${k}</code> <span class="muted">${esc(v)}</span></div>`).join("");
  el.hidden = false;
  el.querySelectorAll(".cmd-row").forEach(r => r.onclick = () => {
    const inp = document.getElementById("chatInput"); inp.value = r.dataset.cmd + " "; el.hidden = true; inp.focus();
  });
}
function initChatWidget() {
  const fab = document.getElementById("chatFab"), panel = document.getElementById("chatPanel");
  if (!fab || !panel) return;
  const open = () => {
    if (!_chat.sid) _newSession();
    panel.classList.add("open"); panel.classList.remove("minimized"); fab.classList.add("hidden");
    _chatClearUnread(); if (!_chat.busy) _chatLight("idle");
    _chatRender(); const i = document.getElementById("chatInput"); if (i) i.focus();
  };
  const close = () => { panel.classList.remove("open", "minimized"); _toggleSessions(false); fab.classList.remove("hidden"); };
  fab.onclick = open;
  document.getElementById("chatClose").onclick = close;
  document.getElementById("chatMin").onclick = () => { panel.classList.toggle("minimized"); if (_chatVisible()) _chatClearUnread(); };
  document.querySelector(".chat-title").onclick = () => { panel.classList.remove("minimized"); _chatClearUnread(); };
  document.getElementById("chatNew").onclick = _newSession;
  document.getElementById("chatSess").onclick = () => _toggleSessions();
  const input = document.getElementById("chatInput");
  input.oninput = (e) => _chatCmdSuggest(e.target.value);
  document.getElementById("chatForm").onsubmit = (e) => {
    e.preventDefault();
    const t = input.value.trim(); input.value = "";
    const hint = document.getElementById("chatCmdHint"); if (hint) hint.hidden = true;
    if (!t) return;
    if (t[0] === "/") _chatRunCommand(t); else _chatSend(t);
  };
}
initChatWidget();
