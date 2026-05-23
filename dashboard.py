#!/usr/bin/env python3
"""
Rich terminal dashboard for polymarket_bot.
Run: python dashboard.py
"""
import sys
import time
import db
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich import box
from metrics.pnl import compute_pnl_summary
from metrics.calibration import compute_calibration
from metrics.sharpe import compute_sharpe

console = Console()


def _color_edge(edge: float) -> Text:
    t = Text(f"{edge:+.3f}")
    if abs(edge) >= 0.08:
        t.stylize("bold green" if edge > 0 else "bold red")
    elif abs(edge) >= 0.05:
        t.stylize("yellow")
    else:
        t.stylize("dim")
    return t


def _color_pnl(v: float) -> Text:
    s = f"${v:+.2f}"
    t = Text(s)
    t.stylize("bold green" if v >= 0 else "bold red")
    return t


def _pct_bar(p: float, width: int = 10) -> str:
    filled = round(p * width)
    return "█" * filled + "░" * (width - filled)


def build_portfolio_panel(pnl: dict, sharpe) -> Panel:
    bankroll = pnl["bankroll"]
    deployed_pct = pnl["deployed"] / (bankroll + pnl["deployed"]) * 100 if (bankroll + pnl["deployed"]) > 0 else 0

    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim")
    t.add_column()

    t.add_row("Bankroll", f"[bold cyan]${bankroll:.2f}[/] USDC")
    t.add_row("Total PnL", _color_pnl(pnl["total_pnl"]))
    t.add_row("Return", Text(f"{pnl['pct_return']:+.1f}%", style="green" if pnl["pct_return"] >= 0 else "red"))
    t.add_row("Deployed", f"[yellow]${pnl['deployed']:.2f}[/]  [dim]{deployed_pct:.0f}% of portfolio[/]")
    t.add_row("Open / Resolved", f"[bold]{pnl['n_open']}[/] / [bold]{pnl['n_resolved']}[/]")

    sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "[dim]N/A (<4 days)[/]"
    t.add_row("Sharpe (ann.)", sharpe_str)

    return Panel(t, title="[bold cyan]Portfolio[/]", border_style="cyan", padding=(0, 1))


def build_performance_panel(pnl: dict, cal: dict) -> Panel:
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim")
    t.add_column()

    wr = pnl["win_rate"]
    wr_style = "green" if wr >= 50 else "red"
    t.add_row("Win Rate", f"[{wr_style}]{wr:.1f}%[/]  [dim]({pnl['n_wins']}W / {pnl['n_losses']}L)[/]")
    t.add_row("Avg Win", _color_pnl(pnl["avg_win"]))
    t.add_row("Avg Loss", _color_pnl(pnl["avg_loss"]))

    acc = cal["accuracy"]
    acc_style = "green" if acc >= 50 else "red"
    t.add_row("Model Accuracy", f"[{acc_style}]{acc:.1f}%[/]  [dim]({cal['model_closer_count']}/{cal['n']})[/]")
    t.add_row("Model vs Mkt err", f"{cal['mean_model_error']:.3f}  vs  {cal['mean_market_error']:.3f}")

    return Panel(t, title="[bold cyan]Performance[/]", border_style="cyan", padding=(0, 1))


def build_positions_table(trades: list) -> Table:
    market_ids = [tr["market_id"] for tr in trades]
    live_prices = db.get_latest_prices_for_markets(market_ids)

    t = Table(
        box=box.SIMPLE_HEAD,
        border_style="bright_black",
        header_style="bold cyan",
        show_footer=False,
        expand=True,
        show_edge=False,
    )
    t.add_column("City", style="bold", min_width=13, no_wrap=True)
    t.add_column("Date", style="dim", min_width=10, no_wrap=True)
    t.add_column("Bucket", no_wrap=True, min_width=16)
    t.add_column("Dir", justify="center", min_width=4)
    t.add_column("Entry", justify="right", min_width=6)
    t.add_column("Now", justify="right", min_width=6)
    t.add_column("Size", justify="right", min_width=7)
    t.add_column("Unreal PnL", justify="right", min_width=10)
    t.add_column("Model", justify="right", min_width=5)
    t.add_column("Edge", justify="right", min_width=6)

    for tr in trades:
        lo = tr["bucket_lo"]
        hi = tr["bucket_hi"]
        unit = tr["bucket_unit"]
        bucket = f"[{lo if lo is not None else '-∞'}, {hi if hi is not None else '+∞'}) {unit}"

        dir_text = Text(tr["direction"])
        dir_text.stylize("bold cyan" if tr["direction"] == "YES" else "bold magenta")

        edge_text = _color_edge(tr["edge"])
        size_style = "bold" if tr["size_usdc"] >= 20 else ""

        price_info = live_prices.get(tr["market_id"])
        if price_info:
            yes_mid, scanned_at = price_info
            current_side_price = yes_mid if tr["direction"] == "YES" else (1.0 - yes_mid)
            shares = tr["size_usdc"] / tr["entry_price"]
            unreal_pnl = shares * current_side_price - tr["size_usdc"]
            now_str = f"{current_side_price:.3f}"
            unreal_text = _color_pnl(unreal_pnl)
        else:
            now_str = "[dim]—[/]"
            unreal_text = Text("[dim]—[/]")

        t.add_row(
            tr["city"],
            str(tr["target_date"]),
            bucket,
            dir_text,
            f"${tr['entry_price']:.3f}",
            now_str,
            Text(f"${tr['size_usdc']:.2f}", style=size_style),
            unreal_text,
            f"{tr['model_prob']:.3f}",
            edge_text,
        )

    return t


def build_city_summary(trades: list) -> Table:
    """Per-city exposure breakdown."""
    from collections import defaultdict
    by_city: dict[str, dict] = defaultdict(lambda: {"deployed": 0.0, "n": 0, "yes": 0, "no": 0})
    for tr in trades:
        c = tr["city"]
        by_city[c]["deployed"] += tr["size_usdc"]
        by_city[c]["n"] += 1
        by_city[c]["yes" if tr["direction"] == "YES" else "no"] += 1

    t = Table(box=box.SIMPLE, header_style="bold cyan", show_edge=False)
    t.add_column("City", style="bold")
    t.add_column("Deployed", justify="right")
    t.add_column("Pos", justify="right")
    t.add_column("YES/NO", justify="center")
    t.add_column("Exposure", no_wrap=True)

    total_deployed = sum(v["deployed"] for v in by_city.values()) or 1
    for city, s in sorted(by_city.items(), key=lambda x: -x[1]["deployed"]):
        bar = _pct_bar(s["deployed"] / total_deployed, 12)
        t.add_row(
            city,
            f"${s['deployed']:.0f}",
            str(s["n"]),
            f"[cyan]{s['yes']}[/]/[magenta]{s['no']}[/]",
            f"[green]{bar}[/]",
        )

    return t


def build_history_table(limit: int = 15) -> Table:
    all_trades = db.get_all_trades()
    resolved = [tr for tr in all_trades if tr["status"] in ("won", "lost", "void")][:limit]

    t = Table(box=box.ROUNDED, border_style="bright_black", header_style="bold cyan", expand=True)
    t.add_column("City", style="bold")
    t.add_column("Date", style="dim")
    t.add_column("Bucket")
    t.add_column("Dir", justify="center")
    t.add_column("Result", justify="center")
    t.add_column("PnL", justify="right")
    t.add_column("Actual", justify="right")

    if not resolved:
        t.add_row("[dim]No resolved trades yet[/]", "", "", "", "", "", "")
        return t

    for tr in resolved:
        pnl = tr["pnl"] or 0.0
        lo = tr["bucket_lo"]
        hi = tr["bucket_hi"]
        unit = tr["bucket_unit"]
        bucket = f"[{lo if lo is not None else '-∞'},{hi if hi is not None else '+∞'}){unit}"

        if tr["status"] == "won":
            result_text = Text("WON", style="bold green")
        elif tr["status"] == "lost":
            result_text = Text("LOST", style="bold red")
        else:
            result_text = Text("VOID", style="dim")

        actual = f"{tr['actual_high_c']:.1f}°C" if tr["actual_high_c"] is not None else "?"
        dir_text = Text(tr["direction"], style="bold cyan" if tr["direction"] == "YES" else "bold magenta")

        t.add_row(
            tr["city"],
            str(tr["target_date"]),
            bucket,
            dir_text,
            result_text,
            _color_pnl(pnl),
            actual,
        )

    return t


def build_stations_table() -> Table:
    stations = db.get_all_stations()
    t = Table(box=box.SIMPLE, header_style="bold cyan", show_edge=False)
    t.add_column("City", style="bold")
    t.add_column("ICAO", style="dim")
    t.add_column("Status", justify="center")
    t.add_column("Days", justify="right")
    t.add_column("Biases", justify="right")
    t.add_column("Avg|Bias|", justify="right")

    for s in sorted(stations, key=lambda x: x["city"]):
        biases = db.get_all_biases(s["icao"])
        n_b = len(biases)
        avg_b = sum(abs(b["bias_c"]) for b in biases) / n_b if biases else 0.0
        status_style = "bold green" if s["status"] == "ready" else "yellow"
        t.add_row(
            s["city"],
            s["icao"],
            Text(s["status"], style=status_style),
            str(s["history_days"]),
            str(n_b),
            f"{avg_b:.2f}°C" if n_b else "—",
        )
    return t


def render_dashboard(mode: str = "paper"):
    console.clear()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    if mode == "both":
        _render_split(now)
        return

    db.set_mode(mode)
    mode_label = "LIVE 🟢" if mode == "live" else "PAPER"
    mode_color = "green" if mode == "live" else "cyan"

    pnl = compute_pnl_summary()
    cal = compute_calibration()
    sharpe = compute_sharpe()
    trades = db.get_open_trades()

    console.print(f"\n[bold {mode_color}]{'═'*70}[/]")
    console.print(f"[bold {mode_color}]  POLYMARKET TEMP BOT  ·  {mode_label}  ·  {now}[/]")
    console.print(f"[bold {mode_color}]{'═'*70}[/]\n")

    # Top row: portfolio + performance side by side
    port_panel = build_portfolio_panel(pnl, sharpe)
    perf_panel = build_performance_panel(pnl, cal)
    console.print(Columns([port_panel, perf_panel], equal=True))
    console.print()

    # Open positions
    if trades:
        console.print(Panel(
            build_positions_table(trades),
            title=f"[bold {mode_color}]Open Positions[/]  [dim]({len(trades)} trades · ${pnl['deployed']:.2f} deployed)[/]",
            border_style=mode_color,
        ))
        console.print()

        # City exposure
        console.print(Panel(
            build_city_summary(trades),
            title=f"[bold {mode_color}]City Exposure[/]",
            border_style="bright_black",
            padding=(0, 1),
        ))
        console.print()
    else:
        console.print("[dim]  No open positions.[/]\n")

    # Trade history
    console.print(Panel(
        build_history_table(),
        title=f"[bold {mode_color}]Recent Trade History[/]",
        border_style="bright_black",
    ))
    console.print()

    if mode != "live":
        # Station status only shown in paper mode (shared across both DBs)
        console.print(Panel(
            build_stations_table(),
            title="[bold cyan]Station Status[/]",
            border_style="bright_black",
            padding=(0, 1),
        ))
        console.print()


def _render_split(now: str):
    """Side-by-side paper vs live summary panel."""
    from rich.rule import Rule

    console.print(f"\n[bold white]{'═'*70}[/]")
    console.print(f"[bold white]  POLYMARKET TEMP BOT  ·  PAPER vs LIVE  ·  {now}[/]")
    console.print(f"[bold white]{'═'*70}[/]\n")

    def _summary(mode):
        db.set_mode(mode)
        pnl = compute_pnl_summary()
        sharpe = compute_sharpe()
        return pnl, sharpe

    pnl_p, sharpe_p = _summary("paper")
    pnl_l, sharpe_l = _summary("live")

    def _panel(pnl, sharpe, mode):
        color = "green" if mode == "live" else "cyan"
        label = "LIVE 🟢" if mode == "live" else "PAPER"
        t = Table.grid(padding=(0, 2))
        t.add_column(style="dim")
        t.add_column()
        t.add_row("Bankroll",    f"[bold {color}]${pnl['bankroll']:.2f}[/]")
        t.add_row("Total PnL",   _color_pnl(pnl["total_pnl"]))
        t.add_row("Return",      Text(f"{pnl['pct_return']:+.1f}%", style="green" if pnl["pct_return"] >= 0 else "red"))
        t.add_row("Deployed",    f"[yellow]${pnl['deployed']:.2f}[/]")
        t.add_row("Open / Res.", f"[bold]{pnl['n_open']}[/] / [bold]{pnl['n_resolved']}[/]")
        t.add_row("Win Rate",    f"{pnl['win_rate']:.1f}%")
        sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "[dim]N/A[/]"
        t.add_row("Sharpe",      sharpe_str)
        return Panel(t, title=f"[bold {color}]{label}[/]", border_style=color, padding=(0, 1))

    console.print(Columns([_panel(pnl_p, sharpe_p, "paper"), _panel(pnl_l, sharpe_l, "live")], equal=True))
    console.print()

    # Show live open positions if any
    db.set_mode("live")
    live_trades = db.get_open_trades()
    if live_trades:
        console.print(Panel(
            build_positions_table(live_trades),
            title=f"[bold green]Live Open Positions[/]  [dim]({len(live_trades)} trades · ${pnl_l['deployed']:.2f})[/]",
            border_style="green",
        ))
        console.print()

    # Show paper open positions
    db.set_mode("paper")
    paper_trades = db.get_open_trades()
    if paper_trades:
        console.print(Panel(
            build_positions_table(paper_trades),
            title=f"[bold cyan]Paper Open Positions[/]  [dim]({len(paper_trades)} trades · ${pnl_p['deployed']:.2f})[/]",
            border_style="cyan",
        ))
        console.print()


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--watch",    action="store_true", help="Refresh every 60s")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--mode",     choices=["paper", "live", "both"], default="paper",
                   help="paper (default), live, or both (split view)")
    args = p.parse_args()

    db.set_mode("paper")  # safe default; render_dashboard will switch as needed
    db.init_db()
    db.set_mode("live")
    db.init_db()
    db.set_mode("paper")  # reset to paper so station status etc. work

    if args.watch:
        try:
            while True:
                render_dashboard(args.mode)
                console.print(f"[dim]  Refreshing in {args.interval}s… (Ctrl+C to quit)[/]\n")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped.[/]")
    else:
        render_dashboard(args.mode)


if __name__ == "__main__":
    main()
