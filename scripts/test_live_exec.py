"""
Manual test harness for live execution integrity (spec 2026-06-10).

NOT part of any CI (there is none). Run directly:

    python scripts/test_live_exec.py

It monkeypatches the py_clob_client seam (broker.live_broker._get_client) and the
orderbook fetch, points db at a THROWAWAY sqlite file, and exercises every fill
outcome end-to-end through the REAL execute_live_trade / sell_position / reconcile
code paths — asserting DB row corrections and bankroll deltas for each.

Scenarios:
  entry: full fill, partial fill, no fill, cancel-race-then-filled, fills-API lag,
         requote-slip abort, NO-token-fetch-failure void
  exit:  resolve-only-on-confirmed-fill, unfilled→held_to_resolution,
         partial-exit→residual-open
  reconcile: pending sweep finalizes a filled order
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import broker.live_broker as lb

PASS, FAIL = "PASS", "FAIL"
_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"  [{PASS if cond else FAIL}] {name}{(' — ' + detail) if detail else ''}")


# ── Fake CLOB client ────────────────────────────────────────────────────────────

class FakeOrder:
    def __init__(self, token_id, price, size, side):
        self.token_id = token_id
        self.price = price
        self.size = size
        self.side = side


class FakeClient:
    """Scriptable fake. `script` controls how each posted order behaves."""

    def __init__(self, script):
        self.script = script              # dict of behaviour knobs
        self._next_id = 1
        self.orders = {}                  # order_id -> state dict
        self.fills = []                   # list of fill dicts
        self.cancelled = set()
        self.poll_counts = {}

    # -- order lifecycle --
    def create_order(self, order_args):
        return order_args                 # pass-through; we sign nothing

    def post_order(self, order_args, order_type):
        oid = f"oid-{self._next_id}"
        self._next_id += 1
        self.orders[oid] = {
            "order_id": oid,
            "size_matched": 0.0,
            "original_size": order_args.size,
            "status": "live",
            "asset_id": order_args.token_id,
            "price": order_args.price,
            "side": getattr(order_args, "side", "BUY"),
        }
        post_status = self.script.get("post_status", "live")
        if post_status in ("matched", "filled"):
            self._fill(oid, order_args.size, order_args.price)
            self.orders[oid]["status"] = post_status
        return {"orderID": oid, "status": post_status}

    def get_order(self, order_id):
        self.poll_counts[order_id] = self.poll_counts.get(order_id, 0) + 1
        st = self.orders.get(order_id, {})
        beh = self.script
        # Apply scripted transitions keyed by poll count.
        n = self.poll_counts[order_id]
        if beh.get("fill_on_poll") and n >= beh["fill_on_poll"] and order_id not in self.cancelled:
            self._fill(order_id, st["original_size"], st["price"])
            st["status"] = "matched"
        if beh.get("partial_on_poll") and n >= beh["partial_on_poll"]:
            part = beh["partial_size"]
            st["size_matched"] = part
            self._record_fill(order_id, part, st["price"])
            st["status"] = "live"
        return dict(st)

    def cancel(self, order_id=None):
        beh = self.script
        if beh.get("cancel_race_fill"):
            # Order fills exactly as we try to cancel it.
            st = self.orders[order_id]
            self._fill(order_id, st["original_size"], st["price"])
            st["status"] = "matched"
            raise RuntimeError("cancel failed: order already matched")
        if beh.get("cancel_error"):
            raise RuntimeError("cancel API error")
        self.cancelled.add(order_id)
        self.orders[order_id]["status"] = "cancelled"

    def get_trades(self, params):
        if self.script.get("fills_lag_until_call"):
            self.script["_fills_calls"] = self.script.get("_fills_calls", 0) + 1
            if self.script["_fills_calls"] < self.script["fills_lag_until_call"]:
                return []
        return list(self.fills)

    def get_orders(self):
        return [dict(o) for o in self.orders.values()
                if o["status"] not in ("cancelled", "canceled")]

    # -- helpers --
    def _fill(self, oid, size, price):
        self.orders[oid]["size_matched"] = size
        self._record_fill(oid, size, price)

    def _record_fill(self, oid, size, price):
        fp = self.script.get("fill_price", price)
        self.fills.append({"order_id": oid, "asset_id": self.orders[oid]["asset_id"],
                           "price": fp, "size": size})


# ── Fixtures ─────────────────────────────────────────────────────────────────────

MARKET = {
    "market_id": "0xCONDITION",
    "clob_token_yes": "TOKEN_YES",
    "city": "Testville", "target_date": "2026-06-15",
    "bucket_lo": 20, "bucket_hi": 21, "bucket_unit": "C",
    "icao": "TEST",
}


def base_signal(direction="NO", entry=0.40, size=15.0):
    return {"direction": direction, "entry_price": entry, "size_usdc": size,
            "model_prob": 0.30, "market_prob": 0.60, "edge": 0.20,
            "ensemble_std_c": 1.0, "kelly_f": 0.05}


def fresh_db():
    """Point db at a throwaway file and init schema."""
    fd, path = tempfile.mkstemp(suffix="_test.db")
    os.close(fd)
    db.DB_PATH = path
    db.set_bankroll  # noqa  (ensure module loaded)
    db.init_db()
    db.set_mode = lambda *a, **k: None   # no-op; we drive DB_PATH directly
    return path


def open_paper_row(direction="NO", entry=0.40, size=15.0):
    """Create the paper row the live path will correct (mirrors paper_broker)."""
    import uuid
    db.upsert_market(MARKET["market_id"], MARKET["city"], "TEST",
                     MARKET["target_date"], "Test market?", 20, 21, "C",
                     MARKET["clob_token_yes"])
    tid = str(uuid.uuid4())
    db.open_trade_atomic(
        trade_id=tid, market_id=MARKET["market_id"], city=MARKET["city"],
        icao="TEST", target_date=MARKET["target_date"], bucket_lo=20, bucket_hi=21,
        bucket_unit="C", direction=direction, entry_price=entry, model_prob=0.30,
        market_prob=0.60, edge=0.20, ensemble_std=1.0, size_usdc=size, kelly_f=0.05,
        clob_token_yes=MARKET["clob_token_yes"])
    return tid


def patch_client(monkey_script, no_token="TOKEN_NO", tick=0.01,
                 requote_ask=None, fail_no_token=False):
    fake = FakeClient(monkey_script)
    lb._get_client = lambda: fake
    # CLOB market response (NO token + tick)
    lb._get_clob_market = lambda mid: ({} if fail_no_token else {
        "tokens": [{"outcome": "Yes", "token_id": "TOKEN_YES"},
                   {"outcome": "No", "token_id": no_token}],
        "minimum_tick_size": tick})
    # Requote orderbook: ask drives slip; bid drives NO-side requote.
    import data.polymarket as pm

    def fake_book(token_id):
        if requote_ask is None:
            return {"bids": [], "asks": []}
        # For a NO trade, _current_ask uses 1 - best_bid; encode the desired NO
        # ask by setting the YES bid to (1 - requote_ask).
        return {"bids": [{"price": str(round(1 - requote_ask, 4)), "size": "500"}],
                "asks": [{"price": str(requote_ask), "size": "500"}]}
    pm.get_clob_orderbook = fake_book
    lb.send_trade_event = lambda *a, **k: None
    lb.send_telegram_notification = lambda *a, **k: None
    # speed up polling
    import config_active as c
    c.LIVE_FILL_POLL_S = 0
    c.LIVE_FILL_TIMEOUT_S = 1
    c.LIVE_EXIT_FILL_TIMEOUT_S = 1
    return fake


def reset_cfg_speed():
    import config_active as c
    c.LIVE_FILL_POLL_S = 0


def apply_entry_result(tid, live_result):
    """Mirror exactly the main.py cmd_scan live-result → DB mapping (WI-2 table),
    so the harness exercises the production correction logic, not a fake."""
    fs = live_result.get("fill_status")
    if "skipped" in live_result:
        db.void_trade_refund_stake(tid, live_result["skipped"])
    elif fs == "filled":
        avg = live_result["avg_fill_price"]
        fsh = live_result["filled_shares"]
        db.update_trade_execution(tid, entry_order_id=live_result.get("order_id"),
                                  entry_fill_status="filled", entry_filled_shares=fsh,
                                  entry_price=avg, size_usdc=round(fsh * avg, 2),
                                  clob_token_no=live_result.get("clob_token_no", ""))
    elif fs == "partial":
        avg = live_result["avg_fill_price"]
        fsh = live_result["filled_shares"]
        db.update_trade_execution(tid, entry_order_id=live_result.get("order_id"),
                                  clob_token_no=live_result.get("clob_token_no", ""))
        db.trim_trade_partial_fill(tid, fsh, avg)
    elif fs == "unfilled":
        db.void_trade_refund_stake(tid, "entry order unfilled")
    elif fs == "pending":
        db.update_trade_execution(tid, entry_order_id=live_result.get("order_id"),
                                  entry_fill_status="pending",
                                  clob_token_no=live_result.get("clob_token_no", ""))


# ── Scenarios ─────────────────────────────────────────────────────────────────────

def scenario_full_fill():
    print("\n== entry: full fill ==")
    fresh_db()
    b0 = db.get_bankroll()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    b_after_stake = db.get_bankroll()
    check("stake deducted at entry", abs((b0 - b_after_stake) - 15.0) < 1e-6,
          f"{b0}->{b_after_stake}")
    patch_client({"fill_on_poll": 1, "fill_price": 0.38}, tick=0.01, requote_ask=0.41)
    res = lb.execute_live_trade(MARKET, base_signal("NO", 0.40, 15.0), trade_id=tid)
    apply_entry_result(tid, res)
    check("returns filled", res.get("fill_status") == "filled", str(res.get("fill_status")))
    row = db.get_all_trades()[0]
    # avg fill 0.38, shares = 15/0.41(rounded up tick)... order_price from requote 0.41
    check("entry_fill_status filled", row["entry_fill_status"] == "filled")
    check("entry_price corrected to avg", abs(row["entry_price"] - 0.38) < 1e-6,
          str(row["entry_price"]))
    check("entry_filled_shares set", row["entry_filled_shares"] and row["entry_filled_shares"] > 0)
    check("size = shares*avg", abs(row["size_usdc"] - round(row["entry_filled_shares"]*0.38, 2)) < 0.01,
          str(row["size_usdc"]))
    check("clob_token_no persisted", row["clob_token_no"] == "TOKEN_NO")
    # bankroll: original stake 15 deducted; refund of (15 - new_size)
    expected_bk = b0 - row["size_usdc"]
    check("bankroll = b0 - filled_size", abs(db.get_bankroll() - expected_bk) < 0.02,
          f"{db.get_bankroll():.2f} vs {expected_bk:.2f}")
    reset_cfg_speed()


def scenario_partial_fill():
    print("\n== entry: partial fill ==")
    fresh_db()
    b0 = db.get_bankroll()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    # order_price after requote/tick. shares requested = 15/price. Fill half.
    patch_client({"partial_on_poll": 1, "partial_size": 18.0, "fill_price": 0.40,
                  "cancel_error": False}, tick=0.01, requote_ask=0.40)
    res = lb.execute_live_trade(MARKET, base_signal("NO", 0.40, 15.0), trade_id=tid)
    apply_entry_result(tid, res)
    check("returns partial", res.get("fill_status") == "partial", str(res.get("fill_status")))
    row = db.get_all_trades()[0]
    check("status partial", row["entry_fill_status"] == "partial")
    check("filled_shares=18", abs((row["entry_filled_shares"] or 0) - 18.0) < 1e-6,
          str(row["entry_filled_shares"]))
    check("size trimmed to 18*0.40", abs(row["size_usdc"] - round(18.0*0.40, 6)) < 0.01,
          str(row["size_usdc"]))
    # bankroll: refund (15 - 7.20) = 7.80 back
    expected_bk = b0 - row["size_usdc"]
    check("bankroll refunded remainder", abs(db.get_bankroll() - expected_bk) < 0.02,
          f"{db.get_bankroll():.2f} vs {expected_bk:.2f}")
    reset_cfg_speed()


def scenario_no_fill():
    print("\n== entry: no fill (void + full refund) ==")
    fresh_db()
    b0 = db.get_bankroll()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    patch_client({}, tick=0.01, requote_ask=0.40)   # never fills
    res = lb.execute_live_trade(MARKET, base_signal("NO", 0.40, 15.0), trade_id=tid)
    apply_entry_result(tid, res)
    check("returns unfilled", res.get("fill_status") == "unfilled", str(res.get("fill_status")))
    row = db.get_all_trades()[0]
    check("status void", row["status"] == "void", row["status"])
    check("entry_fill_status unfilled", row["entry_fill_status"] == "unfilled")
    check("full stake refunded", abs(db.get_bankroll() - b0) < 1e-6,
          f"{db.get_bankroll():.2f} vs {b0:.2f}")
    reset_cfg_speed()


def scenario_cancel_race():
    print("\n== entry: cancel race then filled ==")
    fresh_db()
    b0 = db.get_bankroll()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    # never fills during poll; on cancel it actually fills (race)
    patch_client({"cancel_race_fill": True, "fill_price": 0.40}, tick=0.01, requote_ask=0.40)
    res = lb.execute_live_trade(MARKET, base_signal("NO", 0.40, 15.0), trade_id=tid)
    apply_entry_result(tid, res)
    check("cancel-race resolves to filled", res.get("fill_status") == "filled",
          str(res.get("fill_status")))
    row = db.get_all_trades()[0]
    check("status open (filled)", row["status"] == "open" and row["entry_fill_status"] == "filled")
    reset_cfg_speed()


def scenario_fills_lag():
    print("\n== entry: fills-API lag (retry then fall back ok) ==")
    fresh_db()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    # order fills on poll, but get_trades returns [] for first 2 calls then data.
    patch_client({"fill_on_poll": 1, "fill_price": 0.39, "fills_lag_until_call": 2},
                 tick=0.01, requote_ask=0.40)
    res = lb.execute_live_trade(MARKET, base_signal("NO", 0.40, 15.0), trade_id=tid)
    apply_entry_result(tid, res)
    check("filled despite lag", res.get("fill_status") == "filled", str(res.get("fill_status")))
    row = db.get_all_trades()[0]
    check("avg price from delayed fills (0.39)", abs(row["entry_price"] - 0.39) < 1e-6,
          str(row["entry_price"]))
    reset_cfg_speed()


def scenario_requote_slip():
    print("\n== entry: requote slip abort ==")
    fresh_db()
    b0 = db.get_bankroll()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    # NO ask jumps to 0.45 (slip +0.05 > 0.02) → abort, void.
    patch_client({}, tick=0.01, requote_ask=0.45)
    res = lb.execute_live_trade(MARKET, base_signal("NO", 0.40, 15.0), trade_id=tid)
    apply_entry_result(tid, res)
    check("skipped requote_slip", res.get("skipped") == "requote_slip", str(res))
    reset_cfg_speed()


def scenario_no_token_fail():
    print("\n== entry: NO-token fetch failure ==")
    fresh_db()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    patch_client({}, tick=0.01, requote_ask=0.40, fail_no_token=True)
    res = lb.execute_live_trade(MARKET, base_signal("NO", 0.40, 15.0), trade_id=tid)
    apply_entry_result(tid, res)
    check("skipped no_token_id", res.get("skipped") == "no_token_id_unavailable", str(res))
    reset_cfg_speed()


def scenario_exit_full_fill():
    print("\n== exit: resolve only on confirmed fill ==")
    fresh_db()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    # Mark it as a filled live trade holding 37.5 NO shares.
    db.update_trade_execution(tid, entry_fill_status="filled", entry_filled_shares=37.5,
                              clob_token_no="TOKEN_NO")
    b_pre = db.get_bankroll()
    patch_client({"fill_on_poll": 1, "fill_price": 0.55}, tick=0.01)
    sell = lb.sell_position("TOKEN_NO", 37.5, min_price=0.50, tick=0.01, timeout_s=1)
    check("sell filled", sell.get("fill_status") == "filled", str(sell.get("fill_status")))
    # simulate the exit-scan resolve-on-fill
    db.resolve_trade(tid, None, "won", sell["avg_fill_price"], outcome_source="exit_scan")
    row = db.get_all_trades()[0]
    check("resolved at actual avg (0.55)", abs(row["exit_price"] - 0.55) < 1e-6, str(row["exit_price"]))
    # bankroll credited shares*exit = 37.5*0.55
    check("bankroll += shares*exit", abs(db.get_bankroll() - (b_pre + 37.5*0.55)) < 0.02,
          f"{db.get_bankroll():.2f}")
    reset_cfg_speed()


def scenario_exit_unfilled():
    print("\n== exit: unfilled → held, NOT resolved ==")
    fresh_db()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    db.update_trade_execution(tid, entry_fill_status="filled", entry_filled_shares=37.5,
                              clob_token_no="TOKEN_NO")
    b_pre = db.get_bankroll()
    patch_client({}, tick=0.01)   # never fills
    sell = lb.sell_position("TOKEN_NO", 37.5, min_price=0.50, tick=0.01, timeout_s=1)
    check("sell unfilled", sell.get("fill_status") == "unfilled", str(sell.get("fill_status")))
    row = db.get_all_trades()[0]
    check("trade still open (held)", row["status"] == "open")
    check("bankroll unchanged (no fictional resolve)", abs(db.get_bankroll() - b_pre) < 1e-6)
    reset_cfg_speed()


def scenario_exit_partial():
    print("\n== exit: partial → residual open, proceeds credited ==")
    fresh_db()
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    db.update_trade_execution(tid, entry_fill_status="filled", entry_filled_shares=37.5,
                              clob_token_no="TOKEN_NO")
    b_pre = db.get_bankroll()
    patch_client({"partial_on_poll": 1, "partial_size": 20.0, "fill_price": 0.55}, tick=0.01)
    sell = lb.sell_position("TOKEN_NO", 37.5, min_price=0.50, tick=0.01, timeout_s=1)
    check("sell partial", sell.get("fill_status") == "partial", str(sell.get("fill_status")))
    db.reduce_trade_for_partial_exit(tid, sell["filled_shares"], sell["avg_fill_price"])
    row = db.get_all_trades()[0]
    check("residual open", row["status"] == "open")
    check("residual shares = 17.5", abs((row["entry_filled_shares"] or 0) - 17.5) < 1e-6,
          str(row["entry_filled_shares"]))
    check("proceeds credited (20*0.55)", abs(db.get_bankroll() - (b_pre + 20.0*0.55)) < 0.02,
          f"{db.get_bankroll():.2f}")
    reset_cfg_speed()


def scenario_reconcile_pending():
    print("\n== reconcile: pending sweep finalizes a filled order ==")
    fresh_db()
    db.set_mode_orig = None
    tid = open_paper_row(direction="NO", entry=0.40, size=15.0)
    b0_minus_stake = db.get_bankroll()
    # Mark pending with an order id, as if a daemon died mid-poll.
    db.update_trade_execution(tid, entry_order_id="oid-1", entry_fill_status="pending",
                              clob_token_no="TOKEN_NO")
    fake = patch_client({}, tick=0.01)
    # Inject a filled order matching oid-1 with a recorded fill.
    fake.orders["oid-1"] = {"order_id": "oid-1", "size_matched": 37.5,
                            "original_size": 37.5, "status": "matched",
                            "asset_id": "TOKEN_NO", "price": 0.40, "side": "BUY"}
    fake.fills = [{"order_id": "oid-1", "asset_id": "TOKEN_NO", "price": 0.40, "size": 37.5}]
    # Make balance/position lookups quiet for the bankroll sanity step.
    lb.get_clob_balance = lambda: 0.0
    lb.get_polymarket_positions_value_usd = lambda: 0.0
    lb.get_clob_positions = lambda: [{"asset": "TOKEN_NO", "size": 37.5}]
    summary = lb.reconcile()
    row = db.get_all_trades()[0]
    check("pending finalized to filled", row["entry_fill_status"] == "filled",
          row["entry_fill_status"])
    check("filled_shares=37.5", abs((row["entry_filled_shares"] or 0) - 37.5) < 1e-6,
          str(row["entry_filled_shares"]))
    check("reconcile summary pending>=1", summary["pending_finalized"] >= 1, str(summary))
    reset_cfg_speed()


def main():
    scenario_full_fill()
    scenario_partial_fill()
    scenario_no_fill()
    scenario_cancel_race()
    scenario_fills_lag()
    scenario_requote_slip()
    scenario_no_token_fail()
    scenario_exit_full_fill()
    scenario_exit_unfilled()
    scenario_exit_partial()
    scenario_reconcile_pending()

    n = len(_results)
    failed = [r for r in _results if not r[1]]
    print(f"\n{'='*50}")
    print(f"RESULTS: {n - len(failed)}/{n} checks passed")
    if failed:
        print("FAILURES:")
        for name, _, detail in failed:
            print(f"  - {name} {detail}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
