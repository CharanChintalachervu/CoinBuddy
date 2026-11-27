/* Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE. */
/* Coin Buddy frontend: plain JavaScript, no build step.
   Charts: TradingView Lightweight Charts v5 (Apache-2.0), loaded in index.html. */
"use strict";

(() => {
  const LC = window.LightweightCharts;

  // ------------------------------------------------------------------ utilities
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const qs = (params) =>
    new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString();

  const saved = {
    get(key, fallback) {
      try {
        const v = localStorage.getItem(key);
        return v === null ? fallback : JSON.parse(v);
      } catch {
        return fallback;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, JSON.stringify(value));
      } catch {
        /* private mode or storage blocked: preferences just won't persist */
      }
    },
  };

  function hexA(hex, alpha) {
    const h = hex.replace("#", "");
    const n = parseInt(h.length === 3 ? h.replace(/./g, "$&$&") : h, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }

  function decimalsFor(v) {
    const a = Math.abs(v || 0);
    if (a >= 10) return 2;
    if (a >= 1) return 3;
    if (a >= 0.1) return 4;
    if (a >= 0.01) return 5;
    return 6;
  }
  const nfCache = new Map();
  function fmtPrice(v, d) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const digits = d ?? decimalsFor(v);
    if (!nfCache.has(digits)) {
      nfCache.set(digits, new Intl.NumberFormat("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }));
    }
    return nfCache.get(digits).format(v);
  }
  const compactNf = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });
  const fmtCompact = (v) => (v === null || v === undefined ? "—" : compactNf.format(v));
  // Typographic minus (−) keeps signed numbers the same width as positive ones.
  const fmtPct = (v, d = 2) =>
    v === null || v === undefined ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}%`;
  const fmtSigned = (v, d = 2) => `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`;
  const fmtFrac = (v, d = 2) => (v === null || v === undefined ? "—" : fmtPct(v * 100, d));
  const signClass = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
  const dateTimeFmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const dateFmt = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" });
  const fmtTime = (unix) => dateTimeFmt.format(new Date(unix * 1000));
  const fmtDate = (unix) => dateFmt.format(new Date(unix * 1000));
  // Lightweight Charts renders timestamps as UTC; shift them so the axis shows the viewer's local time.
  const toLocal = (unix) => unix - new Date(unix * 1000).getTimezoneOffset() * 60;
  const tfLabel = (tf) => tf.replace(/h$/, "H").replace(/d$/, "D");

  const COIN_COLORS = { BTC: "#f7931a", ETH: "#627eea", SOL: "#9945ff", BNB: "#d9a400", XRP: "#23292f", DOGE: "#c2a633" };
  function coinColor(base) {
    if (COIN_COLORS[base]) return COIN_COLORS[base];
    let h = 0;
    for (const ch of base) h = (h * 31 + ch.charCodeAt(0)) % 360;
    return `hsl(${h} 55% 48%)`;
  }
  function paintBadges(root) {
    $$(".coin-badge[data-coin]", root).forEach((el) => el.style.setProperty("--coin", coinColor(el.dataset.coin)));
  }

  // ------------------------------------------------------------------ API + toasts
  async function api(path, { method = "GET", body, timeout = 20000 } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(path, {
        method,
        signal: ctrl.signal,
        headers: body ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "That request wasn't valid.";
        throw new Error(res.status >= 500 && !data.detail ? `Server error (${res.status}).` : detail);
      }
      return data;
    } catch (err) {
      if (err.name === "AbortError") throw new Error("The request timed out. Check your connection.");
      if (err instanceof TypeError) throw new Error("Can't reach the Coin Buddy server.");
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  const recentToasts = new Map();
  function toast(message, kind = "error") {
    const now = Date.now();
    if (recentToasts.get(message) > now - 10000) return;
    recentToasts.set(message, now);
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = message;
    $("#toasts").append(el);
    setTimeout(() => el.remove(), 5000);
  }

  // ------------------------------------------------------------------ state
  const state = {
    meta: null,
    exchange: null,
    symbol: null,
    tf: null,
    view: "markets",
    chartType: saved.get("cb-chart-type", "candles"),
    ind: { volume: true, bb: true, signals: true, rsi: true, macd: false, ...saved.get("cb-indicators", {}) },
    watch: [],
    markets: [],
    marketSet: new Set(),
    tickers: {},
    sparks: {},
    lastOk: 0,
    lastSignalAt: 0,
    lastPrice: null,
    ready: false,
  };

  // ------------------------------------------------------------------ live status
  function markOk() {
    state.lastOk = Date.now();
    updateStatus();
  }
  function updateStatus() {
    const el = $("#status");
    const age = (Date.now() - state.lastOk) / 1000;
    const refresh = state.meta ? state.meta.refresh_seconds : 10;
    let cls = "";
    let text = "Connecting";
    if (state.lastOk) {
      if (document.hidden) [cls, text] = ["stale", "Paused"];
      else if (age < refresh * 3) [cls, text] = ["live", "Live"];
      else if (age < 90) [cls, text] = ["stale", "Delayed"];
      else [cls, text] = ["offline", "Offline"];
    }
    el.className = `status ${cls}`;
    $(".status-text", el).textContent = text;
  }

  // ------------------------------------------------------------------ watchlist
  function renderWatchlist() {
    const ul = $("#watchlist");
    if (!state.watch.length) {
      ul.innerHTML = `<li class="watch-empty">Star a market (☆ next to its name) to pin it here.</li>`;
      return;
    }
    ul.innerHTML = state.watch
      .map((sym) => {
        const [base, quote = ""] = sym.split("/");
        return `<li><button class="watch-item" data-symbol="${esc(sym)}" aria-current="${sym === state.symbol}">
          <span class="coin-badge" data-coin="${esc(base)}">${esc(base.slice(0, 1))}</span>
          <span><div class="w-name">${esc(base)}<small>/${esc(quote)}</small></div><div class="w-price num" data-f="price">—</div></span>
          <span class="w-right"><svg class="spark" data-f="spark" viewBox="0 0 64 22" preserveAspectRatio="none" aria-hidden="true"></svg>
          <span class="chg num" data-f="chg">—</span></span></button></li>`;
      })
      .join("");
    paintBadges(ul);
    updateWatchValues();
  }

  function sparkPath(values) {
    const v = values.filter((x) => x !== null);
    if (v.length < 2) return "";
    const min = Math.min(...v);
    const max = Math.max(...v);
    const span = max - min || 1;
    return v.map((x, i) => `${((i / (v.length - 1)) * 64).toFixed(1)},${(20 - ((x - min) / span) * 18).toFixed(1)}`).join(" ");
  }

  function updateWatchValues() {
    $$(".watch-item").forEach((btn) => {
      const sym = btn.dataset.symbol;
      const t = state.tickers[sym];
      if (t) {
        $('[data-f="price"]', btn).textContent = fmtPrice(t.last);
        const chg = $('[data-f="chg"]', btn);
        chg.textContent = fmtPct(t.change_pct);
        chg.className = `chg num ${t.change_pct >= 0 ? "up" : "down"}`;
      }
      const values = state.sparks[sym];
      const svg = $('[data-f="spark"]', btn);
      if (values && values.length > 1 && !svg.childElementCount) {
        const rising = values[values.length - 1] >= values[0];
        svg.innerHTML = `<polyline class="${rising ? "up" : "down"}" points="${sparkPath(values)}"/>`;
      }
    });
  }

  function trackedSymbols() {
    return [...new Set([state.symbol, ...state.watch])].filter(Boolean);
  }

  async function refreshTickers() {
    const list = await api(`/api/tickers?${qs({ symbols: trackedSymbols().join(","), exchange: state.exchange })}`);
    for (const t of list) state.tickers[t.symbol] = t;
    updateWatchValues();
    updateQuote();
    markOk();
  }

  async function refreshSparks() {
    try {
      state.sparks = { ...state.sparks, ...(await api(`/api/sparklines?${qs({ symbols: state.watch.join(","), exchange: state.exchange })}`)) };
      $$(".spark").forEach((s) => (s.innerHTML = ""));
      updateWatchValues();
    } catch {
      /* sparklines are decorative; ignore failures */
    }
  }

  function toggleStar() {
    const i = state.watch.indexOf(state.symbol);
    if (i >= 0) state.watch.splice(i, 1);
    else state.watch.push(state.symbol);
    saved.set("cb-watchlist", state.watch);
    updateStar();
    renderWatchlist();
    if (i < 0) refreshSparks();
  }
  function updateStar() {
    const on = state.watch.includes(state.symbol);
    const star = $("#star");
    star.setAttribute("aria-pressed", String(on));
    const label = on ? "Remove from watchlist" : "Add to watchlist";
    star.title = label;
    star.setAttribute("aria-label", label);
  }

  // ------------------------------------------------------------------ quote header
  function updateQuote() {
    const t = state.tickers[state.symbol];
    const last = chart.rows.length ? chart.rows[chart.rows.length - 1].close : null;
    const price = t?.last ?? last;
    const priceEl = $("#price");
    if (price !== null && price !== undefined) {
      if (state.lastPrice !== null && price !== state.lastPrice) {
        const cls = price > state.lastPrice ? "flash-up" : "flash-down";
        priceEl.classList.remove("flash-up", "flash-down");
        void priceEl.offsetWidth; // restart the transition
        priceEl.classList.add(cls);
        setTimeout(() => priceEl.classList.remove(cls), 700);
      }
      priceEl.textContent = fmtPrice(price);
      state.lastPrice = price;
    }
    const chg = $("#change");
    if (t && t.change_pct !== null) {
      const abs = t.last - t.last / (1 + t.change_pct / 100);
      chg.textContent = `${abs >= 0 ? "+" : "−"}${fmtPrice(Math.abs(abs))} (${fmtPct(t.change_pct)}) 24h`;
      chg.className = `change num ${signClass(t.change_pct)}`;
    } else {
      chg.textContent = "";
    }
    $("#stat-high").textContent = t ? fmtPrice(t.high) : "—";
    $("#stat-low").textContent = t ? fmtPrice(t.low) : "—";
    const quote = state.symbol.split("/")[1] || "";
    $("#stat-vol").textContent = t?.quote_volume ? `${fmtCompact(t.quote_volume)} ${quote}` : "—";
  }

  // ------------------------------------------------------------------ price chart
  const chart = { api: null, series: {}, markers: null, rows: [], rowByTime: new Map(), markerData: [], lastTime: null };

  function colors() {
    return {
      bg: cssVar("--surface"),
      text: cssVar("--muted"),
      strong: cssVar("--text"),
      grid: cssVar("--grid"),
      border: cssVar("--border"),
      faint: cssVar("--faint"),
      up: cssVar("--up"),
      down: cssVar("--down"),
      accent: cssVar("--accent"),
      label: cssVar("--surface-3"),
      warn: cssVar("--warn"),
    };
  }

  function chartOptions(c) {
    return {
      autoSize: true,
      layout: {
        background: { type: LC.ColorType.Solid, color: c.bg },
        textColor: c.text,
        fontFamily: getComputedStyle(document.body).fontFamily,
        fontSize: 11,
        attributionLogo: true,
        panes: { separatorColor: c.border, separatorHoverColor: hexA(c.accent, 0.25), enableResize: true },
      },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false, rightOffset: 6, barSpacing: 8, minBarSpacing: 1.5 },
      crosshair: {
        mode: LC.CrosshairMode.Normal,
        vertLine: { color: c.faint, width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: c.label },
        horzLine: { color: c.faint, width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: c.label },
      },
    };
  }

  function buildChart() {
    if (chart.api) chart.api.remove();
    const c = colors();
    const api_ = LC.createChart($("#chart"), chartOptions(c));
    const s = {};
    const lastClose = chart.rows.length ? chart.rows[chart.rows.length - 1].close : 1;
    const d = decimalsFor(lastClose);
    const priceFormat = { type: "custom", minMove: Math.pow(10, -d), formatter: (v) => fmtPrice(v, d) };
    const quiet = { lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false };

    if (state.chartType === "candles") {
      s.main = api_.addSeries(LC.CandlestickSeries, {
        upColor: c.up, downColor: c.down, wickUpColor: c.up, wickDownColor: c.down, borderVisible: false, priceFormat,
      });
    } else {
      const first = chart.rows.find((r) => r.close !== null);
      const trend = first && lastClose >= first.close ? c.up : c.down;
      s.main = api_.addSeries(LC.AreaSeries, {
        lineColor: trend, topColor: hexA(trend, 0.28), bottomColor: hexA(trend, 0.0), lineWidth: 2, priceFormat,
        crosshairMarkerRadius: 4, crosshairMarkerBorderColor: c.bg,
      });
    }
    s.main.priceScale().applyOptions({ scaleMargins: { top: 0.12, bottom: state.ind.volume ? 0.24 : 0.08 } });

    if (state.ind.volume) {
      s.volume = api_.addSeries(LC.HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "volume", ...quiet });
      s.volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
    }
    if (state.ind.bb) {
      const bbColor = hexA(c.accent, 0.75);
      s.bbUpper = api_.addSeries(LC.LineSeries, { color: bbColor, lineWidth: 1, ...quiet });
      s.bbMid = api_.addSeries(LC.LineSeries, { color: hexA(c.accent, 0.35), lineWidth: 1, lineStyle: LC.LineStyle.Dotted, ...quiet });
      s.bbLower = api_.addSeries(LC.LineSeries, { color: bbColor, lineWidth: 1, ...quiet });
    }
    chart.markers = LC.createSeriesMarkers(s.main, []);

    let pane = 1;
    if (state.ind.rsi) {
      s.rsi = api_.addSeries(
        LC.LineSeries,
        { color: c.accent, lineWidth: 2, priceLineVisible: false, priceFormat: { type: "price", precision: 1, minMove: 0.1 } },
        pane++,
      );
      for (const level of [70, 30]) {
        s.rsi.createPriceLine({ price: level, color: c.faint, lineWidth: 1, lineStyle: LC.LineStyle.Dashed, axisLabelVisible: false });
      }
    }
    if (state.ind.macd) {
      const fmt = { type: "price", precision: d, minMove: Math.pow(10, -d) };
      s.macdHist = api_.addSeries(LC.HistogramSeries, { priceFormat: fmt, ...quiet }, pane);
      s.macd = api_.addSeries(LC.LineSeries, { color: c.accent, lineWidth: 2, priceFormat: fmt, ...quiet }, pane);
      s.macdSignal = api_.addSeries(LC.LineSeries, { color: c.warn, lineWidth: 1, priceFormat: fmt, ...quiet }, pane);
      pane++;
    }
    const panes = api_.panes();
    panes.forEach((p, i) => p.setStretchFactor(i === 0 ? 3.4 : 1));

    api_.subscribeCrosshairMove((param) => {
      const row = param && param.time !== undefined ? chart.rowByTime.get(param.time) : null;
      renderLegend(row || chart.rows[chart.rows.length - 1]);
    });

    chart.api = api_;
    chart.series = s;
  }

  function points(rows, key, extra) {
    return rows.map((r) => {
      const time = toLocal(r.time);
      return r[key] === null ? { time } : { time, value: r[key], ...(extra ? extra(r) : {}) };
    });
  }

  function seriesPayload(rows) {
    const c = colors();
    const s = chart.series;
    const out = [];
    if (state.chartType === "candles") {
      out.push([s.main, rows.map((r) => ({ time: toLocal(r.time), open: r.open, high: r.high, low: r.low, close: r.close }))]);
    } else {
      out.push([s.main, points(rows, "close")]);
    }
    if (s.volume) {
      out.push([s.volume, points(rows, "volume", (r) => ({ color: hexA(r.close >= r.open ? c.up : c.down, 0.32) }))]);
    }
    if (s.bbUpper) {
      out.push([s.bbUpper, points(rows, "bb_upper")], [s.bbMid, points(rows, "bb_mid")], [s.bbLower, points(rows, "bb_lower")]);
    }
    if (s.rsi) out.push([s.rsi, points(rows, "rsi")]);
    if (s.macd) {
      out.push(
        [s.macdHist, points(rows, "macd_hist", (r) => ({ color: hexA(r.macd_hist >= 0 ? c.up : c.down, 0.5) }))],
        [s.macd, points(rows, "macd")],
        [s.macdSignal, points(rows, "macd_signal")],
      );
    }
    return out;
  }

  function applyMarkers() {
    const c = colors();
    const data = state.ind.signals
      ? chart.markerData.map((m) => ({
          time: toLocal(m.time),
          position: m.action === "BUY" ? "belowBar" : "aboveBar",
          color: m.action === "BUY" ? c.up : c.down,
          shape: m.action === "BUY" ? "arrowUp" : "arrowDown",
          text: m.action,
        }))
      : [];
    chart.markers.setMarkers(data);
  }

  function indexRows(rows) {
    chart.rows = rows;
    chart.rowByTime = new Map(rows.map((r) => [toLocal(r.time), r]));
    chart.lastTime = rows.length ? rows[rows.length - 1].time : null;
  }

  function drawAll() {
    buildChart();
    for (const [series, data] of seriesPayload(chart.rows)) series.setData(data);
    applyMarkers();
    renderLegend(chart.rows[chart.rows.length - 1]);
  }

  function renderLegend(row) {
    const el = $("#legend");
    if (!row) {
      el.innerHTML = "";
      return;
    }
    const chg = row.close - row.open;
    const pct = row.open ? (chg / row.open) * 100 : 0;
    const parts = [
      `<span class="lg-extra ${signClass(chg)}">${esc(fmtTime(row.time))}</span>`,
      `<span>O<b>${fmtPrice(row.open)}</b></span>`,
      `<span>H<b>${fmtPrice(row.high)}</b></span>`,
      `<span>L<b>${fmtPrice(row.low)}</b></span>`,
      `<span>C<b>${fmtPrice(row.close)}</b></span>`,
      `<span class="${signClass(chg)}">${fmtPct(pct)}</span>`,
    ];
    if (state.ind.volume) parts.push(`<span class="lg-extra">Vol<b>${fmtCompact(row.volume)}</b></span>`);
    if (state.ind.rsi && row.rsi !== null) parts.push(`<span class="lg-extra">RSI<b>${row.rsi.toFixed(1)}</b></span>`);
    el.innerHTML = parts.join("");
  }

  function setChartOverlay({ loading = false, error = null } = {}) {
    $("#chart-loading").hidden = !loading;
    const errEl = $("#chart-error");
    errEl.hidden = !error;
    if (error) {
      errEl.innerHTML = `<div class="error-box"><p>${esc(error)}</p><button class="btn" type="button">Try again</button></div>`;
      $("button", errEl).addEventListener("click", () => loadChart({ rebuild: true }));
    }
  }

  async function loadChart({ rebuild = true } = {}) {
    const { symbol, tf } = state;
    if (rebuild) setChartOverlay({ loading: true });
    try {
      const data = await api(`/api/candles?${qs({ symbol, timeframe: tf, exchange: state.exchange })}`);
      if (symbol !== state.symbol || tf !== state.tf) return; // user moved on while this loaded
      chart.markerData = data.markers;
      const rows = data.candles;
      const newer = chart.lastTime === null ? [] : rows.filter((r) => r.time >= chart.lastTime);
      if (rebuild || !chart.api || newer.length === 0 || newer.length > 3) {
        indexRows(rows);
        drawAll();
        if (rebuild) chart.api.timeScale().scrollToRealTime();
      } else {
        // Incremental update keeps the user's zoom and scroll position.
        indexRows(rows);
        for (const [series, payload] of seriesPayload(newer)) payload.forEach((p) => series.update(p));
        applyMarkers();
        renderLegend(rows[rows.length - 1]);
      }
      setChartOverlay();
      updateQuote();
      markOk();
    } catch (err) {
      if (rebuild) setChartOverlay({ error: err.message });
      else toast(err.message);
    }
  }

  // ------------------------------------------------------------------ insight cards
  function voteTag(v) {
    return v === 1 ? "BUY" : v === -1 ? "SELL" : "—";
  }

  function renderSignal(s) {
    const n = s.votes.length;
    let headline;
    if (s.action === "BUY") headline = `${s.buy_votes} of ${n} indicators point up`;
    else if (s.action === "SELL") headline = `${s.sell_votes} of ${n} indicators point down`;
    else if (s.buy_votes && s.buy_votes === s.sell_votes) headline = "Indicators disagree";
    else headline = "No clear edge";
    const sub = s.action === "HOLD" ? "Acting needs 2+ votes and a majority." : "Majority vote, 2+ indicators agree.";
    const meter = (label, count, cls) =>
      `<div class="meter"><span>${label}</span><div class="meter-track ${cls}">${[0, 1, 2, 3]
        .map((i) => `<span class="${i < count ? "on" : ""}"></span>`)
        .join("")}</div><span class="num">${count}</span></div>`;
    $("#signal-body").innerHTML = `
      <div class="verdict"><span class="verdict-pill ${s.action}">${s.action}</span>
        <p><strong>${headline}</strong>${sub}</p></div>
      ${meter("Buy", s.buy_votes, "buy")}${meter("Sell", s.sell_votes, "sell")}
      <ul class="votes">${s.votes
        .map(
          (v) => `<li class="vote"><span class="vote-tag ${voteTag(v.value)}">${voteTag(v.value)}</span>
            <div><div class="vote-name">${esc(v.name)}</div><div class="vote-reason num">${esc(v.reason)}</div></div></li>`,
        )
        .join("")}</ul>`;
    $("#signal-meta").textContent = `${tfLabel(s.timeframe)} · closed ${fmtTime(s.candle_close_time)}`;
  }

  function renderML(s) {
    const body = $("#ml-body");
    if (!s.ml) {
      // Models are tied to the exchange, symbol and timeframe they were trained on.
      body.innerHTML = `<p class="muted">No model for ${esc(s.symbol)} ${esc(tfLabel(s.timeframe))} yet.</p>
        <div class="note">Train one on two years of real history:<br>
        <code>coin-buddy train --symbol ${esc(s.symbol)} --timeframe ${esc(s.timeframe)}</code></div>`;
      return;
    }
    const p = s.ml.p_up * 100;
    body.innerHTML = `
      <div class="prob-value num ${p >= 50 ? "up" : "down"}">${p.toFixed(1)}%</div>
      <p class="muted small">chance price rises by more than trading costs over the next ${s.ml.horizon} candles</p>
      <div class="prob-bar"><span class="mid"></span><span class="knob"></span></div>
      <div class="prob-scale"><span>Down</span><span>50%</span><span>Up</span></div>
      <div class="note">Experimental. Check its walk-forward accuracy in <a href="#/backtest">Backtest</a> before trusting it.</div>`;
    $(".knob", body).style.setProperty("--p", `${Math.min(100, Math.max(0, p))}%`);
  }

  function arc(fromDeg, toDeg, r = 52, cx = 65, cy = 70) {
    const pt = (deg) => [cx + r * Math.cos((deg * Math.PI) / 180), cy - r * Math.sin((deg * Math.PI) / 180)];
    const [x1, y1] = pt(fromDeg);
    const [x2, y2] = pt(toDeg);
    return `M${x1.toFixed(2)} ${y1.toFixed(2)} A${r} ${r} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
  }

  function renderSentiment(s) {
    const body = $("#sent-body");
    const sent = s.sentiment;
    $("#sent-meta").textContent = sent.available ? `${sent.posts} posts · ${sent.model.toUpperCase()}` : "";
    if (!sent.available) {
      body.innerHTML = `<p class="muted">Reddit is unreachable right now, so sentiment is sitting this vote out.</p>`;
      return;
    }
    const { sentiment_buy: buyT, sentiment_sell: sellT } = state.meta.thresholds;
    const score = sent.score;
    const [label, cls] =
      score > buyT ? ["Bullish", "up"] : score < sellT ? ["Bearish", "down"]
      : score > 0.05 ? ["Leaning bullish", "up"] : score < -0.05 ? ["Leaning bearish", "down"] : ["Neutral", ""];
    const pos = sent.positive_share * 100;
    const neg = sent.negative_share * 100;
    const neu = Math.max(0, 100 - pos - neg);
    const posts = sent.top_posts
      .map((p) => {
        const chip = p.score > 0.05 ? "pos" : p.score < -0.05 ? "neg" : "neu";
        const safeUrl = /^https:\/\/www\.reddit\.com\//.test(p.url) ? p.url : null;
        const inner = `<div><div class="post-title">${esc(p.title)}</div>
          <div class="post-meta">r/${esc(p.subreddit)} · ${fmtCompact(p.upvotes)} upvotes</div></div>
          <span class="score-chip ${chip} num">${p.score > 0 ? "+" : ""}${p.score.toFixed(2)}</span>`;
        return `<li>${safeUrl ? `<a href="${esc(safeUrl)}" target="_blank" rel="noopener noreferrer">${inner}</a>` : `<a>${inner}</a>`}</li>`;
      })
      .join("");
    body.innerHTML = `
      <div class="gauge-wrap">
        <svg class="gauge" viewBox="0 0 130 80" role="img" aria-label="Sentiment ${score.toFixed(2)} on a scale from -1 to +1">
          <path class="g-neg" d="${arc(180, 124)}"/><path class="g-neu" d="${arc(116, 64)}"/><path class="g-pos" d="${arc(56, 0)}"/>
          <g class="needle"><line x1="65" y1="70" x2="65" y2="26"/><circle cx="65" cy="70" r="5"/></g>
        </svg>
        <div><div class="mood-label ${cls}">${label}</div>
          <div class="mood-score num">Score ${score > 0 ? "+" : ""}${score.toFixed(3)} (−1 to +1)</div></div>
      </div>
      <div class="mix"><span class="pos"></span><span class="neu"></span><span class="neg"></span></div>
      <div class="mix-legend num"><span class="up">${pos.toFixed(0)}% positive</span><span>${neu.toFixed(0)}% neutral</span><span class="down">${neg.toFixed(0)}% negative</span></div>
      <ul class="posts">${posts}</ul>`;
    $(".mix .pos", body).style.setProperty("--w", `${pos}%`);
    $(".mix .neu", body).style.setProperty("--w", `${neu}%`);
    $(".mix .neg", body).style.setProperty("--w", `${neg}%`);
    const needle = $(".needle", body);
    requestAnimationFrame(() => (needle.style.transform = `rotate(${Math.max(-1, Math.min(1, score)) * 90}deg)`));
  }

  function insightSkeletons() {
    $("#signal-body").innerHTML = `<div class="skeleton h-lg"></div><div class="skeleton"></div><div class="skeleton"></div>`;
    $("#ml-body").innerHTML = `<div class="skeleton"></div>`;
    $("#sent-body").innerHTML = `<div class="skeleton h-lg"></div><div class="skeleton"></div>`;
    $("#signal-meta").textContent = "Analysing…";
  }

  async function loadSignal() {
    const { symbol, tf } = state;
    state.lastSignalAt = Date.now();
    try {
      const s = await api(`/api/signal?${qs({ symbol, timeframe: tf, exchange: state.exchange })}`, { timeout: 60000 });
      if (symbol !== state.symbol || tf !== state.tf) return;
      renderSignal(s);
      renderML(s);
      renderSentiment(s);
    } catch (err) {
      $("#signal-body").innerHTML = `<p class="muted">${esc(err.message)}</p>`;
      $("#signal-meta").textContent = "";
    }
  }

  // ------------------------------------------------------------------ symbol / timeframe selection
  function resolveSymbol(input) {
    const raw = input.trim().toUpperCase();
    if (!raw) return null;
    if (!state.markets.length) return raw.includes("/") ? raw : `${raw}/USDT`;
    if (state.marketSet.has(raw)) return raw;
    return state.markets.find((m) => m.startsWith(`${raw}/`)) || state.markets.find((m) => m.startsWith(raw)) || null;
  }

  function updateURL() {
    const hash = location.hash || "#/markets";
    history.replaceState(null, "", `?${qs({ symbol: state.symbol, tf: state.tf })}${hash}`);
  }

  function selectSymbol(symbol) {
    state.symbol = symbol;
    state.lastPrice = null;
    saved.set("cb-symbol", symbol);
    updateURL();
    const [base] = symbol.split("/");
    $("#sym-name").textContent = symbol;
    const badge = $("#coin-badge");
    badge.textContent = base.slice(0, 1);
    badge.dataset.coin = base;
    paintBadges(badge.parentElement);
    $("#price").textContent = "—";
    $("#change").textContent = "";
    $$(".watch-item").forEach((b) => b.setAttribute("aria-current", String(b.dataset.symbol === symbol)));
    updateStar();
    chart.lastTime = null;
    insightSkeletons();
    loadChart({ rebuild: true });
    loadSignal();
    refreshTickers().catch((err) => toast(err.message));
  }

  function selectTimeframe(tf) {
    state.tf = tf;
    saved.set("cb-tf", tf);
    $$("#tf-seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tf === tf)));
    updateURL();
    chart.lastTime = null;
    insightSkeletons();
    loadChart({ rebuild: true });
    loadSignal();
  }

  async function loadMarkets() {
    try {
      state.markets = await api(`/api/markets?${qs({ exchange: state.exchange })}`, { timeout: 30000 });
      state.marketSet = new Set(state.markets);
      $("#market-list").innerHTML = state.markets.slice(0, 3000).map((m) => `<option value="${esc(m)}">`).join("");
    } catch {
      /* search still works with typed symbols */
    }
  }

  // ------------------------------------------------------------------ polling
  let pollTimer = null;
  function schedule() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(tick, state.meta.refresh_seconds * 1000);
  }
  async function tick() {
    if (!document.hidden && state.view === "markets") {
      await Promise.allSettled([refreshTickers(), loadChart({ rebuild: false })]);
      if (Date.now() - state.lastSignalAt > 60000) loadSignal();
    }
    schedule();
  }

  // ------------------------------------------------------------------ backtest
  const bt = { days: 365, strategy: "both", report: null, active: 0, chart: null };
  const RESULT_LABELS = { rules: "Rules", ml: "ML model", "rules (ML test window)": "Rules · ML window" };

  function setSeg(container, attr, value) {
    $$(`button`, container).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset[attr] === String(value))));
  }

  async function runBacktest(ev) {
    ev.preventDefault();
    const symbol = resolveSymbol($("#bt-symbol").value);
    if (!symbol) {
      toast("Pick a market listed on this exchange.");
      return;
    }
    $("#bt-symbol").value = symbol;
    const runBtn = $("#bt-run");
    runBtn.disabled = true;
    runBtn.lastChild.textContent = " Running…";
    $("#bt-output").innerHTML = `<div class="card progress">
        <div class="progress-bar"><span></span></div>
        <strong>Replaying ${esc(symbol)} over ${bt.days} days</strong>
        <p class="muted small">Downloading history${bt.strategy !== "rules" ? " and training the model walk-forward" : ""}. This can take up to a minute.</p>
      </div>`;
    try {
      const report = await api(`/api/backtest?${qs({ exchange: state.exchange })}`, {
        method: "POST",
        body: { symbol, timeframe: $("#bt-tf").value, days: bt.days, strategy: bt.strategy },
        timeout: 300000,
      });
      bt.report = report;
      bt.active = 0;
      renderBacktest();
    } catch (err) {
      $("#bt-output").innerHTML = `<div class="card empty"><h3>Backtest failed</h3><p class="muted">${esc(err.message)}</p></div>`;
    } finally {
      runBtn.disabled = false;
      runBtn.lastChild.textContent = " Run backtest";
    }
  }

  function renderBacktest() {
    const r = bt.report;
    if (!r.results.length) {
      $("#bt-output").innerHTML = `<div class="card empty"><h3>Not enough history</h3><p class="muted">Try a longer period or a shorter timeframe.</p></div>`;
      return;
    }
    $("#bt-output").innerHTML = `
      <div class="result-tabs">
        <div><h3>${esc(r.symbol)} · ${tfLabel(r.timeframe)} · ${fmtDate(r.start)} – ${fmtDate(r.end)}</h3>
          <p class="muted small">${r.candles.toLocaleString()} candles · ${(r.costs.fee * 100).toFixed(2)}% fee + ${(r.costs.slippage * 100).toFixed(2)}% slippage per side</p></div>
        <div class="seg" id="bt-result-seg" role="group" aria-label="Result">${r.results
          .map((x, i) => `<button type="button" data-i="${i}" aria-pressed="${i === bt.active}">${esc(RESULT_LABELS[x.name] || x.name)}</button>`)
          .join("")}</div>
      </div>
      <div id="bt-detail" class="page"></div>`;
    $$("#bt-result-seg button").forEach((b) =>
      b.addEventListener("click", () => {
        bt.active = Number(b.dataset.i);
        setSeg($("#bt-result-seg"), "i", bt.active);
        renderResult();
      }),
    );
    renderResult();
  }

  function kpi(label, value, cls, sub) {
    return `<div class="card kpi"><div class="kpi-label">${label}</div><div class="kpi-value num ${cls || ""}">${value}</div>
      <div class="kpi-sub num">${sub || "&nbsp;"}</div></div>`;
  }

  function renderResult() {
    const r = bt.report;
    const res = r.results[bt.active];
    const m = res.metrics;
    const beat = m.total_return - m.buy_and_hold_return;
    let insight;
    if (m.return_before_costs > 0 && m.total_return < 0) {
      insight = ["bad", "A real edge, eaten by costs",
        `Before costs this made ${fmtFrac(m.return_before_costs)}, but ${m.round_trips} round trips paid about ${(m.costs_paid * 100).toFixed(1)}% of capital in fees and slippage. Trading less often is the first thing to try.`];
    } else if (beat > 0) {
      insight = ["good", "Beat buy & hold",
        `Returned ${fmtFrac(m.total_return)} vs ${fmtFrac(m.buy_and_hold_return)} for holding. It was in the market ${(m.exposure * 100).toFixed(0)}% of the time; sitting in cash during a falling market can explain an outperformance on its own.`];
    } else {
      insight = ["bad", "No edge after costs",
        `Returned ${fmtFrac(m.total_return)} vs ${fmtFrac(m.buy_and_hold_return)} for simply holding over the same period.`];
    }
    if (res.name === "ml" && r.walk_forward) {
      const wf = r.walk_forward;
      insight[2] += ` Out-of-sample accuracy was ${(wf.accuracy * 100).toFixed(1)}% vs ${(wf.baseline * 100).toFixed(1)}% for a naive baseline, over ${wf.folds} walk-forward folds.`;
    }
    const trades = res.trades
      .map(
        (t) => `<tr><td>${fmtTime(t.entry_time)}</td><td>${fmtTime(t.exit_time)}</td>
          <td class="r num">${fmtPrice(t.entry_price)}</td><td class="r num">${fmtPrice(t.exit_price)}</td>
          <td class="r"><span class="chg num ${t.net_return >= 0 ? "up" : "down"}">${fmtFrac(t.net_return)}</span></td></tr>`,
      )
      .join("");
    $("#bt-detail").innerHTML = `
      <div class="kpis">
        ${kpi("Return after costs", fmtFrac(m.total_return), signClass(m.total_return), `Buy & hold ${fmtFrac(m.buy_and_hold_return)}`)}
        ${kpi("Return before costs", fmtFrac(m.return_before_costs), signClass(m.return_before_costs), `Costs ≈ ${(m.costs_paid * 100).toFixed(1)}% of capital`)}
        ${kpi("vs buy & hold", `${beat >= 0 ? "+" : "−"}${Math.abs(beat * 100).toFixed(1)} pts`, signClass(beat), beat >= 0 ? "Outperformed" : "Underperformed")}
        ${kpi("Max drawdown", fmtFrac(m.max_drawdown), "down", `Buy & hold ${fmtFrac(m.buy_and_hold_max_drawdown)}`)}
        ${kpi("Sharpe ratio", fmtSigned(m.sharpe), signClass(m.sharpe), `Buy & hold ${fmtSigned(m.buy_and_hold_sharpe)}`)}
        ${kpi("Win rate", `${(m.win_rate * 100).toFixed(1)}%`, "", `${m.round_trips} round trips`)}
        ${kpi("Average trade", fmtFrac(m.avg_trade_return), signClass(m.avg_trade_return), "after costs")}
        ${kpi("Time in market", `${(m.exposure * 100).toFixed(1)}%`, "", "rest of the time in cash")}
      </div>
      <div class="card insight ${insight[0]}"><div><strong>${insight[1]}</strong><span class="muted">${esc(insight[2])}</span></div></div>
      <div class="card equity-card">
        <div class="card-head"><h2>Portfolio value</h2>
          <div class="equity-legend"><span><i></i>Strategy</span><span><i class="bh"></i>Buy & hold</span></div></div>
        <div class="equity-chart" id="equity-chart"></div>
      </div>
      <div class="card table-card">
        <div class="card-head"><h2>Trades</h2><span class="muted small">${res.trades.length ? "Most recent first" : ""}</span></div>
        ${res.trades.length ? `<div class="table-scroll"><table><thead><tr><th>Entry</th><th>Exit</th><th class="r">Entry price</th><th class="r">Exit price</th><th class="r">Return</th></tr></thead><tbody>${trades}</tbody></table></div>` : `<div class="empty"><p>No trades in this period.</p></div>`}
      </div>`;
    drawEquity(res);
  }

  function drawEquity(res) {
    if (bt.chart) bt.chart.remove();
    const el = $("#equity-chart");
    if (!el) return;
    const c = colors();
    const opts = chartOptions(c);
    opts.timeScale = { ...opts.timeScale, timeVisible: false, rightOffset: 0, fixLeftEdge: true, fixRightEdge: true };
    const ch = LC.createChart(el, opts);
    const fmt = { type: "custom", minMove: 1, formatter: (v) => fmtPrice(v, 0) };
    const bh = ch.addSeries(LC.LineSeries, { color: c.faint, lineWidth: 2, lineStyle: LC.LineStyle.Dashed, priceFormat: fmt, priceLineVisible: false });
    const strat = ch.addSeries(LC.AreaSeries, {
      lineColor: c.accent, topColor: hexA(c.accent, 0.22), bottomColor: hexA(c.accent, 0), lineWidth: 2, priceFormat: fmt, priceLineVisible: false,
    });
    const map = (pts) => pts.map((p) => ({ time: toLocal(p.time), value: p.value }));
    bh.setData(map(res.benchmark));
    strat.setData(map(res.equity));
    // Fit after layout: the container only gets its real width once it's in the page.
    requestAnimationFrame(() => ch.timeScale().fitContent());
    bt.chart = ch;
  }

  // ------------------------------------------------------------------ history
  async function loadHistory() {
    const body = $("#history-body");
    body.innerHTML = `<div class="progress"><div class="spinner"></div></div>`;
    try {
      const rows = await api("/api/history?limit=300");
      if (!rows.length) {
        body.innerHTML = `<div class="empty"><h3>No signals yet</h3><p>Open the Markets view or run <code>coin-buddy watch</code>. Every signal is saved here.</p></div>`;
        return;
      }
      body.innerHTML = `<div class="table-scroll"><table><thead><tr>
          <th>Time</th><th>Market</th><th>Timeframe</th><th class="r">Price</th><th class="r">RSI</th>
          <th class="r">Sentiment</th><th class="r">ML P(up)</th><th>Signal</th></tr></thead><tbody>${rows
            .map(
              (r) => `<tr><td>${esc(dateTimeFmt.format(new Date(r.taken_at)))}</td><td>${esc(r.symbol)} <span class="muted small">${esc(r.exchange)}</span></td>
              <td>${esc(tfLabel(r.timeframe))}</td><td class="r num">${fmtPrice(r.price)}</td>
              <td class="r num">${r.rsi === null ? "—" : r.rsi.toFixed(1)}</td>
              <td class="r num ${signClass(r.sentiment)}">${r.sentiment === null ? "—" : r.sentiment.toFixed(3)}</td>
              <td class="r num">${r.ml_p_up === null ? "—" : `${(r.ml_p_up * 100).toFixed(1)}%`}</td>
              <td><span class="action-chip ${esc(r.action)}">${esc(r.action)}</span></td></tr>`,
            )
            .join("")}</tbody></table></div>`;
    } catch (err) {
      body.innerHTML = `<div class="empty"><h3>Couldn't load history</h3><p>${esc(err.message)}</p></div>`;
    }
  }

  // ------------------------------------------------------------------ routing
  function route() {
    const view = location.hash.replace(/^#\/?/, "").split("?")[0] || "markets";
    state.view = ["markets", "backtest", "history"].includes(view) ? view : "markets";
    $$(".view").forEach((s) => (s.hidden = s.id !== `view-${state.view}`));
    $$(".nav-link").forEach((a) => (a.dataset.view === state.view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    if (state.view === "history") loadHistory();
    if (state.view === "backtest" && !$("#bt-symbol").value) {
      $("#bt-symbol").value = state.symbol;
      $("#bt-tf").value = state.tf;
    }
    if (state.view === "markets" && state.ready) tick();
  }

  // ------------------------------------------------------------------ theme
  function toggleTheme() {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("cb-theme", next);
    } catch {
      /* ignore */
    }
    if (chart.rows.length) drawAll();
    if (bt.report && $("#equity-chart")) drawEquity(bt.report.results[bt.active]);
  }

  // ------------------------------------------------------------------ wiring
  function bindEvents() {
    $("#watchlist").addEventListener("click", (e) => {
      const item = e.target.closest(".watch-item");
      if (item && item.dataset.symbol !== state.symbol) selectSymbol(item.dataset.symbol);
    });
    $("#star").addEventListener("click", toggleStar);
    $("#theme-toggle").addEventListener("click", toggleTheme);

    const search = $("#search");
    const go = () => {
      const sym = resolveSymbol(search.value);
      if (!sym) {
        toast(`No market matching "${search.value}" on ${state.exchange}.`);
        return;
      }
      search.value = "";
      search.blur();
      if (location.hash !== "#/markets") location.hash = "#/markets";
      if (sym !== state.symbol) selectSymbol(sym);
    };
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
      if (e.key === "Escape") search.blur();
    });
    search.addEventListener("change", () => state.marketSet.has(search.value.toUpperCase()) && go());

    document.addEventListener("keydown", (e) => {
      const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        search.focus();
      }
    });

    $("#tf-seg").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (b && b.dataset.tf !== state.tf) selectTimeframe(b.dataset.tf);
    });
    $("#type-seg").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || b.dataset.type === state.chartType) return;
      state.chartType = b.dataset.type;
      saved.set("cb-chart-type", state.chartType);
      setSeg($("#type-seg"), "type", state.chartType);
      if (chart.rows.length) drawAll();
    });
    $("#ind-chips").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      state.ind[b.dataset.ind] = !state.ind[b.dataset.ind];
      saved.set("cb-indicators", state.ind);
      b.setAttribute("aria-pressed", String(state.ind[b.dataset.ind]));
      if (chart.rows.length) drawAll();
    });

    $("#bt-form").addEventListener("submit", runBacktest);
    $("#bt-days").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      bt.days = Number(b.dataset.days);
      setSeg($("#bt-days"), "days", bt.days);
    });
    $("#bt-strategy").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      bt.strategy = b.dataset.strategy;
      setSeg($("#bt-strategy"), "strategy", bt.strategy);
    });
    $("#history-refresh").addEventListener("click", loadHistory);

    window.addEventListener("hashchange", route);
    document.addEventListener("visibilitychange", () => {
      updateStatus();
      if (!document.hidden) tick();
    });
  }

  function fatal(message) {
    $("main").innerHTML = `<div class="card empty"><h3>Coin Buddy can't start</h3><p>${esc(message)}</p></div>`;
  }

  async function init() {
    if (!LC) {
      fatal("The chart library didn't load. Check your internet connection and reload.");
      return;
    }
    try {
      state.meta = await api("/api/meta");
    } catch (err) {
      fatal(err.message);
      return;
    }
    const m = state.meta;
    const params = new URLSearchParams(location.search);
    state.exchange = m.exchange;
    state.symbol = (params.get("symbol") || saved.get("cb-symbol", m.symbol)).toUpperCase();
    const tf = params.get("tf") || saved.get("cb-tf", m.timeframe);
    state.tf = m.timeframes.includes(tf) ? tf : m.timeframe;
    state.watch = saved.get("cb-watchlist", null) || [...m.watchlist];

    $("#exchange-pill").textContent = m.exchange;
    $("#version").textContent = `v${m.version}`;
    $("#disclaimer").textContent = m.disclaimer;
    $("#bt-costs").textContent = `${(m.costs.fee * 100).toFixed(2)}% fees + ${(m.costs.slippage * 100).toFixed(2)}% slippage per side`;
    $("#tf-seg").innerHTML = m.timeframes
      .map((t) => `<button type="button" data-tf="${t}" aria-pressed="${t === state.tf}">${tfLabel(t)}</button>`)
      .join("");
    $("#bt-tf").innerHTML = m.timeframes.filter((t) => t !== "1m").map((t) => `<option value="${t}">${tfLabel(t)}</option>`).join("");
    setSeg($("#type-seg"), "type", state.chartType);
    $$("#ind-chips button").forEach((b) => b.setAttribute("aria-pressed", String(!!state.ind[b.dataset.ind])));

    bindEvents();
    renderWatchlist();
    selectSymbol(state.symbol);
    route();
    state.ready = true;
    schedule();
    loadMarkets();
    refreshSparks();
    setInterval(refreshSparks, 5 * 60 * 1000);
    setInterval(updateStatus, 1000);
  }

  init();
})();
