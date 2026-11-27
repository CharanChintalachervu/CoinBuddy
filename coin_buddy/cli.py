# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Command-line interface: `coin-buddy <command>` (or `python -m coin_buddy <command>`)."""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from coin_buddy import __copyright__, __version__, ml
from coin_buddy.alerts import notify
from coin_buddy.backtest import format_metrics
from coin_buddy.config import Config, load_config
from coin_buddy.data.market import fetch_history, make_exchange
from coin_buddy.indicators import add_indicators
from coin_buddy.pipeline import backtest, take_snapshot
from coin_buddy.storage import Store

DISCLAIMER = "Educational tool. Not financial advice. Coin Buddy never places trades."


def _apply_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    for attr in ("exchange", "symbol", "timeframe"):
        value = getattr(args, attr, None)
        if value:
            setattr(cfg.market, attr, value)
    return cfg


def cmd_snapshot(cfg: Config, args: argparse.Namespace) -> int:
    store = Store(cfg.resolve(cfg.storage.database))
    snap = take_snapshot(cfg, store=store)
    row = snap.latest
    print(
        f"\n{cfg.market.symbol} on {cfg.market.exchange} ({cfg.market.timeframe})  "
        f"candle closed {row.name:%Y-%m-%d %H:%M} UTC"
    )
    print(f"  Price      {row['close']:,.2f}")
    s = snap.sentiment
    if s.n_posts:
        print(
            f"  Sentiment  {s.score:+.3f} from {s.n_posts} posts "
            f"({s.positive_share:.0%} positive, {s.negative_share:.0%} negative, model: {cfg.sentiment.model})"
        )
    else:
        print("  Sentiment  unavailable (Reddit unreachable); sentiment abstains")
    if snap.ml_p_up is not None:
        print(f"  ML model   P(up over next {cfg.ml.horizon_candles} candles) = {snap.ml_p_up:.1%}")
    print(f"\nSignal: {snap.signal.explain()}\n\n{DISCLAIMER}")
    return 0


def cmd_watch(cfg: Config, args: argparse.Namespace) -> int:
    store = Store(cfg.resolve(cfg.storage.database))
    print(f"Watching {cfg.market.symbol} every {args.interval}s. Ctrl+C to stop. {DISCLAIMER}")
    last_action = None
    try:
        while True:
            try:
                snap = take_snapshot(cfg, store=store)
            except Exception as exc:  # noqa: BLE001 - keep watching through transient failures
                logging.getLogger(__name__).error("Snapshot failed: %s", exc)
            else:
                action = snap.signal.action.value
                print(
                    f"[{snap.taken_at:%H:%M:%S}] {snap.latest['close']:,.2f}  "
                    f"sentiment {snap.sentiment.score:+.3f}  -> {action} "
                    f"({snap.signal.buy_votes} buy / {snap.signal.sell_votes} sell)"
                )
                if action != last_action:  # alert on changes only, not every repeat
                    notify(action, f"Coin Buddy: {cfg.market.symbol} {snap.signal.explain()}", cfg.alerts)
                last_action = action
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_backtest(cfg: Config, args: argparse.Namespace) -> int:
    strategies = ("rules", "ml") if args.strategy == "both" else (args.strategy,)
    report = backtest(cfg, args.days, strategies)
    c = report.candles
    print(
        f"\nBacktest: {cfg.market.symbol} {cfg.market.timeframe} on {cfg.market.exchange}, "
        f"{c.index[0]:%Y-%m-%d} to {c.index[-1]:%Y-%m-%d} ({len(c):,} candles)"
    )
    print(f"Costs: {cfg.backtest.fee_rate:.2%} fee + {cfg.backtest.slippage_rate:.2%} slippage per side\n")
    for name, res in report.results.items():
        span = f"{res.equity.index[0]:%Y-%m-%d} to {res.equity.index[-1]:%Y-%m-%d}"
        print(f"[{name}]  {span}\n{format_metrics(res.metrics)}\n")
    wf = report.walk_forward
    if wf and wf.folds:
        edge = wf.accuracy - wf.baseline_accuracy
        print(
            f"ML walk-forward: {wf.folds} folds, out-of-sample accuracy {wf.accuracy:.1%} "
            f"vs naive baseline {wf.baseline_accuracy:.1%} ({edge:+.1%})\n"
        )
    if args.report and report.results:
        from coin_buddy.charts import equity_chart, price_chart
        from coin_buddy.signals import action_series

        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        title = f"{cfg.market.symbol} {cfg.market.timeframe}: strategy vs buy & hold"
        equity_html = equity_chart(report.results, title).to_html(full_html=False, include_plotlyjs="cdn")
        tail = c.tail(500)
        price_html = price_chart(tail, action_series(tail, cfg.strategy), "Last 500 candles with rule signals").to_html(
            full_html=False, include_plotlyjs=False
        )
        out.write_text(
            f"<html><head><meta charset='utf-8'><title>Coin Buddy backtest</title></head>"
            f"<body style='font-family:sans-serif;max-width:1200px;margin:auto'>"
            f"<h1>Coin Buddy backtest</h1><p>{DISCLAIMER}</p>{equity_html}{price_html}</body></html>",
            encoding="utf-8",
        )
        print(f"Report written to {out.resolve()}")
    print(DISCLAIMER)
    return 0


def cmd_train(cfg: Config, args: argparse.Namespace) -> int:
    m = cfg.market
    candles = add_indicators(
        fetch_history(m.symbol, m.timeframe, args.days, exchange=make_exchange(m.exchange)), cfg.indicators
    )
    path = ml.train_and_save(
        candles,
        cfg.ml,
        cfg.backtest,
        cfg.model_file(),
        {"symbol": m.symbol, "timeframe": m.timeframe, "exchange": m.exchange, "trained_until": str(candles.index[-1])},
    )
    print(f"Model trained on {len(candles):,} candles and saved to {path}")
    print("Check `coin-buddy backtest --strategy ml` to see whether it beats a naive baseline out of sample.")
    return 0


def cmd_dashboard(cfg: Config, args: argparse.Namespace) -> int:
    import threading
    import webbrowser

    import uvicorn

    from coin_buddy.web.server import create_app

    host = args.host or cfg.web.host
    port = args.port or cfg.web.port
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    print(f"Coin Buddy dashboard running at {url}  (Ctrl+C to stop)")
    if args.open:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="warning")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="coin-buddy",
        description="Crypto signals with honest backtesting.",
        epilog=__copyright__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}\n{__copyright__}")
    p.add_argument("--config", help="Path to a config YAML (default: config.yaml)")
    p.add_argument("-v", "--verbose", action="store_true", help="Show debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    def market_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--exchange", help="ccxt exchange id, e.g. kraken")
        sp.add_argument("--symbol", help="e.g. ETH/USDT")
        sp.add_argument("--timeframe", help="e.g. 15m, 1h, 4h")

    sp = sub.add_parser("snapshot", help="Print the current signal with a full explanation")
    market_opts(sp)
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("watch", help="Re-check on an interval, store history and alert on changes")
    market_opts(sp)
    sp.add_argument("--interval", type=int, default=300, help="Seconds between checks (default 300)")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("backtest", help="Test strategies on real history with fees and slippage")
    market_opts(sp)
    sp.add_argument("--days", type=int, default=365)
    sp.add_argument("--strategy", choices=["rules", "ml", "both"], default="both")
    sp.add_argument(
        "--report",
        nargs="?",
        const="reports/backtest.html",
        help="Write an interactive HTML report (default path: reports/backtest.html)",
    )
    sp.set_defaults(func=cmd_backtest)

    sp = sub.add_parser("train", help="Train the ML model on real history and save it")
    market_opts(sp)
    sp.add_argument("--days", type=int, default=730)
    sp.set_defaults(func=cmd_train)

    sp = sub.add_parser("dashboard", help="Launch the web dashboard")
    sp.add_argument("--host", help="Interface to bind (default from config; 0.0.0.0 for all)")
    sp.add_argument("--port", type=int, help="Port (default 8000)")
    sp.add_argument("--open", action="store_true", help="Open the dashboard in your browser")
    sp.set_defaults(func=cmd_dashboard)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = _apply_overrides(load_config(args.config), args)
    return args.func(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
