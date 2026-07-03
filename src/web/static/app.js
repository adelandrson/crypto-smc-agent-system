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
  return `<div class="dtable-wrap"><table class="dtable"><thead>${t.thead}</thead><tbody>${slice.map(t.rowFn).join("")}</tbody></table></div>${nav}`;
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
document.getElementById("searchForm").onsubmit = e => { e.preventDefault(); analyze(document.getElementById("symInput").value.trim()); };

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

async function analyze(symbol) {
  if (!symbol) return;
  const sym = symbol.trim().toUpperCase();
  _activeSym = sym;
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
    out.innerHTML = html;
  } catch (e) {
    out.innerHTML = `<p class="muted">gagal memuat analisa: ${esc(String(e))}</p>`;
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
  const thead = `<tr><th>Koin</th><th>Tier Scalp</th><th>Tier Swing</th><th class="r">Mcap</th><th class="r">Volume 24h</th><th class="r">CMC Rank</th></tr>`;
  const badge = t => `<span class="tier-badge ${esc(t || "")}">${esc(t || "—")}</span>`;
  const rowFn = r => `<tr><td><b>${esc(r.symbol)}</b> <span class="muted">${esc(r.name || "")}</span></td>
    <td>${badge(r.scalp_tier)}</td><td>${badge(r.swing_tier)}</td>
    <td class="r">$${fmtUsd(r.market_cap)}</td><td class="r">$${fmtUsd(r.volume_24h)}</td>
    <td class="r muted">${r.cmc_rank ?? "—"}</td></tr>`;
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
    <div class="pos-head"><span class="pos-sym">${esc(p.symbol)} <span class="muted">${esc(p.group)} · ${p.leg === "long" ? "LONG" : "SHORT"} · ${p.leverage}x</span></span>
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
  const dir = p.leg === "long" ? "LONG" : "SHORT";
  return `<div class="pos-card pending">
    <div class="pos-head"><span class="pos-sym">${esc(p.symbol)} <span class="muted">${esc(p.group)} · ${dir} · ${p.leverage}x</span></span>
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
        <div class="ac-big">$${s.equity.toFixed(2)} <small>${s.return_pct >= 0 ? "+" : ""}${s.return_pct}%</small></div>
        <div class="ac-grid"><div><span>Open</span><b>${s.open}</b></div><div><span>Closed</span><b>${s.closed}</b></div>
          <div><span>Win-rate</span><b>${s.win_rate != null ? s.win_rate + "%" : "—"}</b></div>
          <div><span>Leverage</span><b>${esc(s.leverage_range)}</b></div></div>
        <div class="ac-expectancy">Expectancy: <b>${s.expectancy_r != null ? (s.expectancy_r > 0 ? "+" : "") + s.expectancy_r + "R" : "belum cukup sampel"}</b></div>
      </div>`).join("")}</div>`;
    let html = "";
    if (d.pending && d.pending.length) html += `<h3 class="ag-h">LIMIT order menunggu (${d.pending.length})</h3>` + d.pending.map(_pendingCard).join("");
    if (d.open && d.open.length) html += `<h3 class="ag-h">Posisi terbuka (${d.open.length})</h3>` + d.open.map(_posCard).join("");
    else if (!(d.pending && d.pending.length)) html += `<p class="muted">Tidak ada posisi terbuka atau limit order menunggu.</p>`;
    if (d.closed && d.closed.length) {
      const thead = `<tr><th>Koin</th><th>Gaya</th><th>Arah</th><th class="r">PnL</th><th class="r">R</th><th>Outcome</th><th>Ditutup</th></tr>`;
      const rowFn = r => `<tr><td><b>${esc(r.symbol)}</b></td><td class="muted">${esc(r.group)}</td>
        <td>${r.leg === "long" ? '<span class="pos">LONG</span>' : '<span class="neg">SHORT</span>'}</td>
        <td class="r ${(r.realized_pnl_usd || 0) >= 0 ? "pos" : "neg"}">$${(r.realized_pnl_usd || 0).toFixed(2)}</td>
        <td class="r">${r.r_multiple != null ? r.r_multiple + "R" : "—"}</td><td class="muted">${esc(r.outcome || "")}</td>
        <td class="muted">${r.closed_at ? new Date(r.closed_at).toLocaleString() : ""}</td></tr>`;
      html += pagedTable("closed", "Riwayat tertutup", thead, d.closed, rowFn);
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
