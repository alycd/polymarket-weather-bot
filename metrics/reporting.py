"""
Terminal dashboard using tabulate.
All ANSI color, no external UI libraries.
"""
import math
from datetime import datetime
from tabulate import tabulate
from metrics.pnl import compute_pnl_summary
from metrics.calibration import compute_calibration
from metrics.sharpe import compute_sharpe
import db

G = "\033[92m"   # green
R = "\033[91m"   # red
Y = "\033[93m"   # yellow
C = "\033[96m"   # cyan
B = "\033[1m"    # bold
DIM = "\033[2m"  # dim
RST = "\033[0m"  # reset


def cpnl(v):
    s = f"${v:+.2f}"
    return f"{G}{s}{RST}" if v >= 0 else f"{R}{s}{RST}"


def cpct(v):
    s = f"{v:+.1f}%"
    return f"{G}{s}{RST}" if v >= 0 else f"{R}{s}{RST}"


def crate(v):
    s = f"{v:.1f}%"
    return f"{G}{s}{RST}" if v >= 50 else f"{R}{s}{RST}"


def _bar(prob, width=12):
    filled = round(prob * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {prob*100:.0f}%"


def _per_city_stats(trades: list) -> list:
    """
    Group resolved trades by city and compute profitability stats.
    Returns a list of formatted table rows sorted by total PnL descending.
    Only includes cities with at least 1 resolved trade.
    """
    from collections import defaultdict
    city_data: dict = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0,
                                            "total_pnl": 0.0, "entry_sum": 0.0})
    for t in trades:
        city = t.get("city", "Unknown")
        city_data[city]["trades"] += 1
        if t["status"] == "won":
            city_data[city]["wins"] += 1
        elif t["status"] == "lost":
            city_data[city]["losses"] += 1
        city_data[city]["total_pnl"] += t.get("pnl") or 0.0
        city_data[city]["entry_sum"] += t.get("entry_price") or 0.0

    rows = []
    for city, d in city_data.items():
        n = d["trades"]
        if n == 0:
            continue
        win_rate = d["wins"] / n * 100
        avg_entry = d["entry_sum"] / n
        win_rate_str = f"{G}{win_rate:.1f}%{RST}" if win_rate >= 50 else f"{R}{win_rate:.1f}%{RST}"
        pnl_str = (f"{G}${d['total_pnl']:+.2f}{RST}" if d["total_pnl"] >= 0
                   else f"{R}${d['total_pnl']:+.2f}{RST}")
        rows.append((city, n, d["wins"], d["losses"], win_rate_str, pnl_str,
                     f"${avg_entry:.3f}", d["total_pnl"]))

    # Sort by total_pnl descending, then strip the sort key
    rows.sort(key=lambda r: r[7], reverse=True)
    return [r[:7] for r in rows]


def print_stats():
    pnl = compute_pnl_summary()
    cal = compute_calibration()
    sharpe = compute_sharpe()

    print(f"\n{B}{C}{'─'*60}{RST}")
    print(f"{B}{C}  POLYMARKET TEMP BOT — METRICS DASHBOARD{RST}")
    print(f"{B}{C}{'─'*60}{RST}")
    print(f"  {DIM}{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}{RST}\n")

    # Portfolio
    br = pnl["bankroll"]
    print(f"{B}Portfolio{RST}")
    print(f"  Bankroll:          {B}${br:.2f}{RST} USDC")
    print(f"  Total PnL:         {cpnl(pnl['total_pnl'])} ({cpct(pnl['pct_return'])})")
    print(f"  Deployed:          ${pnl['deployed']:.2f}  ({pnl['n_open']} open)")
    print(f"  Resolved trades:   {pnl['n_resolved']}\n")

    # Performance
    wr_str = crate(pnl['win_rate'])
    sharpe_str = f"{sharpe:.2f}" if sharpe is not None else f"{DIM}N/A (<4 days){RST}"
    print(f"{B}Performance{RST}")
    print(f"  Win Rate:          {wr_str}  ({pnl['n_wins']}W / {pnl['n_losses']}L)")
    print(f"  Avg Win:           {cpnl(pnl['avg_win'])}")
    print(f"  Avg Loss:          {cpnl(pnl['avg_loss'])}")
    print(f"  Sharpe (ann.):     {sharpe_str}")

    # Calibration
    acc_color = G if cal["accuracy"] >= 50 else R
    print(f"\n{B}Signal Calibration{RST}")
    print(f"  Model closer than market: "
          f"{acc_color}{cal['accuracy']:.1f}%{RST} "
          f"({cal['model_closer_count']}/{cal['n']})")
    print(f"  Mean model error:  {cal['mean_model_error']:.3f}")
    print(f"  Mean market error: {cal['mean_market_error']:.3f}")

    # By city calibration
    if cal["by_city"]:
        print(f"\n{B}Calibration by City{RST}")
        cal_rows = []
        for city, s in sorted(cal["by_city"].items()):
            pct = s["closer"] / s["n"] * 100 if s["n"] else 0
            cal_rows.append([city, s["n"], s["closer"], f"{pct:.0f}%"])
        print(tabulate(cal_rows, headers=["City", "Trades", "Model Better", "Accuracy"],
                       tablefmt="simple"))
    print()

    # Per-city profitability
    resolved_trades = db.get_resolved_trades()
    city_rows = _per_city_stats(resolved_trades)
    if city_rows:
        print(f"{B}Profitability by City{RST}")
        print(tabulate(city_rows,
                       headers=["City", "Trades", "W", "L", "Win%", "PnL", "Avg Entry"],
                       tablefmt="simple"))
        print()

    # Bias corrections overview
    stations = db.get_all_stations()
    if stations:
        print(f"{B}Station Status{RST}")
        st_rows = []
        for s in stations:
            biases = db.get_all_biases(s["icao"])
            n_biases = len(biases)
            avg_abs_bias = (sum(abs(b["bias_c"]) for b in biases) / n_biases
                           if biases else 0.0)
            status_color = G if s["status"] == "ready" else Y
            st_rows.append([
                s["city"],
                s["icao"],
                f"{status_color}{s['status']}{RST}",
                s["history_days"],
                n_biases,
                f"{avg_abs_bias:.2f}°C" if n_biases else "—",
            ])
        print(tabulate(st_rows,
                       headers=["City", "ICAO", "Status", "Days", "#Biases", "Avg|Bias|"],
                       tablefmt="rounded_outline"))
    print()


def print_positions():
    trades = db.get_open_trades()
    bankroll = db.get_bankroll()
    deployed = sum(t["size_usdc"] for t in trades)

    print(f"\n{B}{C}OPEN POSITIONS{RST}")
    print(f"  Bankroll: {B}${bankroll:.2f}{RST}  |  Deployed: ${deployed:.2f}"
          f"  |  {len(trades)} positions\n")

    if not trades:
        print(f"  {DIM}No open positions.{RST}\n")
        return

    rows = []
    for t in trades:
        edge_color = G if abs(t["edge"]) >= 0.08 else (Y if abs(t["edge"]) >= 0.05 else DIM)
        dir_color = C if t["direction"] == "YES" else "\033[95m"
        lo = t["bucket_lo"]
        hi = t["bucket_hi"]
        unit = t["bucket_unit"]
        deg = "°" + unit
        if lo is None and hi is not None:
            temp_str = f"< {hi}{deg}"
        elif hi is None and lo is not None:
            temp_str = f"≥ {lo}{deg}"
        else:
            temp_str = f"{lo}–{hi}{deg}"
        bet = f"{dir_color}{t['direction']}{RST} {temp_str}"
        rows.append([
            t["trade_id"][:8],
            t["city"],
            str(t["target_date"]),
            bet,
            f"${t['entry_price']:.3f}",
            f"${t['size_usdc']:.2f}",
            f"{t['model_prob']:.3f}",
            f"{t['market_prob']:.3f}",
            f"{edge_color}{t['edge']:+.3f}{RST}",
            t["entry_time"][11:16],
        ])

    print(tabulate(rows,
                   headers=["ID", "City", "Resolves", "Bet",
                             "Entry", "Size", "Model", "Mkt", "Edge", "At"],
                   tablefmt="rounded_outline"))
    print()


def print_history(limit=30):
    all_trades = db.get_all_trades()
    resolved = [t for t in all_trades if t["status"] in ("won", "lost", "void")][:limit]

    print(f"\n{B}{C}TRADE HISTORY{RST}\n")
    if not resolved:
        print(f"  {DIM}No resolved trades.{RST}\n")
        return

    rows = []
    total_pnl = 0.0
    for t in resolved:
        pnl = t["pnl"] or 0.0
        total_pnl += pnl
        result_str = (f"{G}WON{RST}" if t["status"] == "won" else
                      (f"{R}LOST{RST}" if t["status"] == "lost" else f"{DIM}VOID{RST}"))
        lo = t["bucket_lo"]
        hi = t["bucket_hi"]
        unit = t["bucket_unit"]
        bucket = f"[{lo or '-∞'},{hi or '+∞'}){unit}"
        actual = f"{t['actual_high_c']:.1f}°C" if t["actual_high_c"] is not None else "?"
        rows.append([
            t["trade_id"][:8],
            t["city"],
            str(t["target_date"]),
            bucket,
            t["direction"],
            f"${t['entry_price']:.3f}",
            f"${t['size_usdc']:.2f}",
            result_str,
            f"${pnl:+.2f}",
            actual,
            (t["resolved_at"] or "")[:10],
        ])

    print(tabulate(rows,
                   headers=["ID", "City", "Date", "Bucket", "Dir",
                             "Entry", "Size", "Result", "PnL", "Actual", "Resolved"],
                   tablefmt="rounded_outline"))
    wins  = sum(1 for t in resolved if t["status"] == "won")
    print(f"\n  Trades: {len(resolved)}  |  Wins: {wins}  |  PnL: {cpnl(total_pnl)}\n")


def print_calibration():
    """
    Full calibration curve report.
    Shows bucketed predicted-vs-actual win rate, per-market-type breakdown,
    bias direction, and a shrinkage factor recommendation.
    """
    from metrics.calibration import compute_calibration_curve, compute_calibration

    curve  = compute_calibration_curve()
    cal    = compute_calibration()

    print(f"\n{B}{C}{'─'*64}{RST}")
    print(f"{B}{C}  CALIBRATION CURVE REPORT{RST}")
    print(f"{B}{C}{'─'*64}{RST}")
    print(f"  {DIM}{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}{RST}")
    print(f"  Resolved trades: {B}{curve['n_total']}{RST}  |  "
          f"Brier: {B}{cal['model_brier']:.4f}{RST}  |  "
          f"BSS: {B}{cal['brier_skill_score']:+.4f}{RST}\n")

    if curve["n_total"] < 5:
        print(f"  {Y}Not enough resolved trades for calibration curve (need ≥5).{RST}\n")
        return

    # ── Overall calibration curve ─────────────────────────────────────────────
    print(f"{B}Calibration Curve — All Markets{RST}")
    print(f"  (Each row = trades where model said P(win) is in that range)")
    print(f"  {'Range':<12} {'Predicted':>10} {'Actual':>10} {'Bias':>8} {'N':>5}  {'Visual'}")
    print(f"  {'─'*12} {'─'*10} {'─'*10} {'─'*8} {'─'*5}  {'─'*28}")

    for b in curve["buckets"]:
        bias = b["bias"]
        bias_color = (G if bias > 0.02 else (R if bias < -0.02 else DIM))
        bias_label = f"{bias_color}{bias:+.3f}{RST}"

        # Visual bar showing actual vs predicted
        bar_w = 20
        pred_filled  = round(b["predicted"] * bar_w)
        actual_filled = round(b["actual"] * bar_w)
        bar = "█" * actual_filled + "░" * (bar_w - actual_filled)
        marker = f"↑{b['predicted']:.0%}"

        print(f"  {b['range']:<12} {b['predicted']:>9.1%} {b['actual']:>9.1%} "
              f"  {bias_label:>8}  {b['n']:>4}  {bar} {marker}")

    # ── Bias summary ──────────────────────────────────────────────────────────
    if curve["overall_bias"] is not None:
        ob = curve["overall_bias"]
        if abs(ob) < 0.02:
            bias_msg = f"{G}Well-calibrated (bias={ob:+.3f}){RST}"
        elif ob < 0:
            bias_msg = (f"{R}Overconfident (bias={ob:+.3f}) — "
                        f"model claims more certainty than it has{RST}")
        else:
            bias_msg = (f"{Y}Underconfident (bias={ob:+.3f}) — "
                        f"model is more accurate than it thinks{RST}")
        print(f"\n  Overall bias: {bias_msg}")

    if curve["shrinkage_factor"] is not None:
        sf = curve["shrinkage_factor"]
        if abs(sf - 1.0) < 0.05:
            sf_msg = f"{G}{sf:.3f} (no correction needed){RST}"
        elif sf < 1.0:
            sf_msg = (f"{R}{sf:.3f} — shrink (model_prob - 0.5) by {(1-sf)*100:.1f}% "
                      f"before computing edge{RST}")
        else:
            sf_msg = (f"{Y}{sf:.3f} — model is conservative; edge may be understated{RST}")
        print(f"  Shrinkage factor: {sf_msg}")

    # ── Per market type breakdown ─────────────────────────────────────────────
    if curve["by_market_type"]:
        print(f"\n{B}Breakdown by Market Type{RST}")
        for mt, data in curve["by_market_type"].items():
            mt_label = mt.upper()
            ob = data.get("overall_bias")
            ob_str = f"{ob:+.3f}" if ob is not None else "N/A"
            ob_color = (G if ob is not None and ob > 0.02 else
                        (R if ob is not None and ob < -0.02 else DIM))
            print(f"\n  {B}{mt_label}{RST}  ({data['n']} trades, bias={ob_color}{ob_str}{RST})")

            if not data["buckets"]:
                print(f"    {DIM}Not enough data per bucket (need ≥5 per range).{RST}")
                continue

            print(f"    {'Range':<12} {'Predicted':>10} {'Actual':>10} {'Bias':>8} {'N':>5}")
            print(f"    {'─'*12} {'─'*10} {'─'*10} {'─'*8} {'─'*5}")
            for b in data["buckets"]:
                bias = b["bias"]
                bc = G if bias > 0.02 else (R if bias < -0.02 else DIM)
                print(f"    {b['range']:<12} {b['predicted']:>9.1%} {b['actual']:>9.1%} "
                      f"  {bc}{bias:+.3f}{RST}  {b['n']:>4}")

    # ── Win rate check ────────────────────────────────────────────────────────
    print(f"\n{B}Signal vs Market Summary{RST}")
    print(f"  Model better than market: "
          f"{''+G if cal['accuracy']>=50 else R}"
          f"{cal['accuracy']:.1f}%{RST} of trades "
          f"({cal['model_closer_count']}/{cal['n']})")
    print(f"  Mean model error:   {cal['mean_model_error']:.4f}")
    print(f"  Mean market error:  {cal['mean_market_error']:.4f}")
    print(f"  Brier skill score:  "
          f"{''+G if cal['brier_skill_score']>0 else R}"
          f"{cal['brier_skill_score']:+.4f}{RST}  "
          f"{DIM}(>0 = better than market){RST}")
    print()


def print_cities():
    from config import CITIES
    stations = db.get_all_stations()
    status_map = {s["icao"]: s for s in stations}

    rows = []
    for city, cfg in sorted(CITIES.items()):
        icao = cfg["icao"]
        st = status_map.get(icao)
        if st:
            status = f"{G if st['status']=='ready' else Y}{st['status']}{RST}"
            days = st["history_days"]
        else:
            status = f"{DIM}not_loaded{RST}"
            days = 0
        rows.append([
            city, icao, cfg["asos_station"],
            f"{cfg['lat']:.2f}°", f"{cfg['lon']:.2f}°",
            "°F" if cfg["uses_fahrenheit"] else "°C",
            status, days,
        ])

    print(f"\n{B}{C}CITY CONFIGURATION{RST}\n")
    print(tabulate(rows,
                   headers=["City", "ICAO", "ASOS", "Lat", "Lon", "Unit", "Status", "Days"],
                   tablefmt="rounded_outline"))
    print()
