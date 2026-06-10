# Live Execution Integrity — Spec

**Date:** 2026-06-10
**Status:** SPEC — not implemented
**Scope:** live mode only. Paper mode behavior must be bit-for-bit unchanged.
**Motivation:** audit of the live order path found that live trading is structurally
fire-and-forget: orders are submitted and assumed filled, NO exits sell a token we
don't hold, and the DB resolves trades regardless of whether anything happened
on-chain. The DB bankroll can diverge arbitrarily from the real wallet.

---

## 1. Findings being fixed (with current code references)

| # | Severity | Finding | Where |
|---|----------|---------|-------|
| F1 | CRITICAL | Live NO exits sell `clob_token_yes` — a token we don't hold for NO positions. The CLOB rejects the SELL (insufficient balance); the DB still resolves the trade and credits estimated P&L. Most of the book is NO bets. | `main.py:1314-1316` |
| F2 | CRITICAL | Entry fills are assumed, never verified. `filled_price = order_price` under a comment that says "Poll for fill". `FILL_TIMEOUT_S=30` is defined but unused; the docstring's cancel-and-repost strategy is unimplemented. | `live_broker.py:37, 290-292` |
| F3 | CRITICAL | Order IDs and the NO token ID are discarded. `main.py` prints the live result and throws it away; nothing in the DB ties a trade to a CLOB order, so reconciliation/cancellation is impossible after the fact. | `main.py:805-812`, `live_broker.py:226` |
| F4 | HIGH | Stale GTC entry orders are never cancelled. An unfilled buy rests indefinitely and fills exactly when the market moves through it — i.e., after the forecast moved against us (pure adverse selection). 30-min opportunistic scans run 24/7, so these accumulate. | `cancel_order`/`get_open_orders`/`get_order_status` exist in `live_broker.py:305-374` with **zero call sites** |
| F5 | HIGH | Exits resolve in DB regardless of fill. Sell is a GTC limit at `0.95 × exit_val`, no polling, then `db.resolve_trade` immediately. Unfilled sell → DB credits money that never arrived. | `main.py:1308-1321` |
| F6 | HIGH | CLOSING-SOON exits fire into the thinnest book of the day. `CLOSE_SOON_HOURS=2` → sells posted 10pm–midnight local, when T+0 max-temp outcomes are already known and books are pinned/one-sided. Worse: when no live price is available, `exit_val` falls back to `entry_price`, so the sell is posted at `0.95 × entry` — a price unrelated to the market — and the DB resolves at that fictional price. | `main.py:1204, 1280-1281, 1297-1298` |
| F7 | MEDIUM | Exit share count is recomputed as `size_usdc / entry_price` from DB values, not actual filled shares. With partial fills or entry rounding (`round(shares, 2)`), the sell can exceed real holdings → rejected outright. | `main.py:1300`, `live_broker.py:240` |
| F8 | MEDIUM | Partial fills recorded as full fills. Entry size > depth at ask → partial fill on-chain; DB records full `size_usdc` at full price. | `live_broker.py:290-292` |
| F9 | MEDIUM | `sync_positions_to_db` is log-only (detects "trade in DB, not on CLOB" but repairs nothing), reachable only via manual `--sync-positions`, and never scheduled by the daemon. No automated DB↔chain reconciliation exists. | `live_broker.py:449-485`, `main.py:1412-1430`, `daemon.py:38-61` |
| F10 | LOW | Entry price snapshot is stale by submission time. The ask is captured at scan start; the scan loops over ~40 cities before submitting. | `main.py` scan loop |
| F11 | LOW | Tick-size handling: prices are rounded to 0.01; markets with 0.001 ticks near 0/1 can have an "ask" we round below, turning a taker order into a resting one. | `live_broker.py:223, 237, 390` |
| F12 | LOW | Dead code: NO `order_price` computed from `market_prob` then immediately overwritten. Docstring claims orders post "at mid-price"; actual entry price is the ask (YES) / 1−bid (NO) from `edge_calculator.py:367-369`. | `live_broker.py:13-16, 229-231` |

### Relevant existing mechanics (do not break)

- Trade insert: `db.open_trade_atomic` (`db.py:791`) — deducts stake AND inserts the
  row in one transaction. Called from `paper_broker.py:221-242`, which already
  persists `clob_token_yes`. `execute_paper_trade` returns `trade_id`
  (`paper_broker.py:259-268`), which the live path currently ignores.
- Bankroll accounting (`db.resolve_trade`, `db.py:725-770`): **stake is
  pre-deducted at entry**. `won`/`stop_loss` → `bankroll += shares * exit_price`
  where `shares = size_usdc / entry_price`. This means: if we correct
  `entry_price` and `size_usdc` to actual fill values, all downstream P&L math
  stays consistent with no other changes.
- Schema migrations are guarded `ALTER TABLE` statements in `db.py` init
  (pattern at `db.py:227-271`).
- Entry depth gate already exists in paper risk checks
  (`MIN_BOOK_DEPTH_USDC = 150`, top-5 levels, `paper_broker.py:38-64`) — it runs
  before the live order too, since live submission happens only after
  `execute_paper_trade` succeeds (`main.py:783-805`).

---

## 2. Goals / non-goals

**Goals**
1. Every live trade row in the DB reflects an actual on-chain fill (price, size, shares) or is voided.
2. NO positions exit by selling the NO token we actually hold.
3. No GTC order outlives its usefulness: unfilled orders are cancelled within a bounded window.
4. Trade exits resolve in the DB only at prices that were actually achieved (or at protocol resolution).
5. An automated reconciliation loop detects and repairs DB↔chain divergence and alerts on what it can't repair.
6. Paper mode untouched: identical code path, identical outputs, identical DB writes.

**Non-goals**
- No change to signal generation, edge math, sizing, or any risk gate (those are governed by separate forward tests — see `docs/plans/2026-06-09_forward_tests.md`).
- No market-making / passive-fill optimization (we stay a taker; the docstring's mid-price passive strategy is abandoned, not implemented).
- No backfill/repair of historical live trades (one-time manual audit is a rollout step, not code).
- No FOK/FAK order types in v1 (see Open Questions).

---

## 3. Design

### WI-1 — Schema: persist execution identity on `trades`

New columns (guarded `ALTER TABLE` migration in `db.py` init, following the
`db.py:227-271` pattern). All default to NULL/'' so paper rows are unaffected:

```sql
ALTER TABLE trades ADD COLUMN clob_token_no       TEXT NOT NULL DEFAULT '';
ALTER TABLE trades ADD COLUMN entry_order_id      TEXT NOT NULL DEFAULT '';
ALTER TABLE trades ADD COLUMN entry_fill_status   TEXT NOT NULL DEFAULT '';
        -- '' (paper / pre-migration) | 'pending' | 'filled' | 'partial' | 'unfilled'
ALTER TABLE trades ADD COLUMN entry_filled_shares REAL;          -- actual shares held on-chain
ALTER TABLE trades ADD COLUMN exit_order_id       TEXT NOT NULL DEFAULT '';
ALTER TABLE trades ADD COLUMN exit_fill_status    TEXT NOT NULL DEFAULT '';
        -- '' | 'pending' | 'filled' | 'partial' | 'unfilled' | 'held_to_resolution'
```

New `db.py` helpers (no raw SQL outside db.py, per project convention):

```python
def update_trade_execution(trade_id, *, clob_token_no=None, entry_order_id=None,
                           entry_fill_status=None, entry_filled_shares=None,
                           entry_price=None, size_usdc=None,
                           exit_order_id=None, exit_fill_status=None): ...
def void_trade_refund_stake(trade_id, reason): ...
    # status='void', bankroll += size_usdc, notes += reason — single transaction.
    # (resolve_trade('void') already does the bankroll math; this wraps it with
    #  fill-status bookkeeping and an EXIT-less audit log entry.)
def trim_trade_partial_fill(trade_id, filled_shares, fill_price): ...
    # entry_price=fill_price, size_usdc=filled_shares*fill_price,
    # entry_filled_shares=filled_shares, refund (orig_size - new_size) to bankroll —
    # single transaction.
```

`shares = size_usdc / entry_price` in `resolve_trade` then automatically equals
`entry_filled_shares` for corrected rows. For exits, prefer
`entry_filled_shares` when set, falling back to the division for legacy rows.

### WI-2 — Entry: verify the fill, correct the DB, cancel the remainder

Rewrite the tail of `execute_live_trade` (`live_broker.py:256-302`) and the call
site (`main.py:803-812`).

**In `execute_live_trade`:**

1. **Re-quote at submission time (F10):** fetch the current book for the token
   (`data/polymarket.get_clob_orderbook` already exists). For BUY-YES use the
   current best ask; for BUY-NO use the NO book's best ask (equivalently
   1 − YES best bid). If the re-quoted price is worse than the scan-time
   `signal["entry_price"]` by more than `LIVE_MAX_REQUOTE_SLIP` (new config,
   default **0.02**), return `{"skipped": "requote_slip"}` — the edge was
   computed against a price that no longer exists.
2. **Tick-size aware rounding (F11):** fetch the market's tick size
   (`GET /markets/{condition_id}` already used in `_get_no_token_id` — reuse the
   response; tick is in `minimum_tick_size`). Round the BUY limit **up** to the
   next tick at-or-above the quoted ask (taker intent), SELL limits **down**.
3. **Post GTC at the re-quoted ask**, then **poll** `get_order_status(order_id)`
   every `LIVE_FILL_POLL_S` (default **3s**) for up to `FILL_TIMEOUT_S`
   (existing constant, **30s** — finally used). The CLOB order object exposes
   `size_matched`; terminal when `size_matched == size` or status is
   `matched`/`filled`.
4. **Outcome handling:**
   - **Filled:** compute actual average fill price from `get_clob_fills`
     filtered by order id (fills can execute across book levels). Return
     `{order_id, fill_status: 'filled', filled_shares, avg_fill_price}`.
   - **Partial:** `cancel_order(order_id)` for the remainder, then return
     `{fill_status: 'partial', filled_shares: size_matched, avg_fill_price}`.
   - **Unfilled:** `cancel_order(order_id)`, return `{fill_status: 'unfilled'}`.
   - **Cancel fails** (race: filled while cancelling): re-check status once;
     treat as filled/partial per `size_matched`. If the cancel API errors and
     status is unknown, return `{fill_status: 'pending', order_id}` — the
     reconciler (WI-5) owns it from there. Never guess.
5. Keep the existing telegram `LIVE-TRADE` event but send it **after** fill
   confirmation, with actual fill price/size, and a distinct
   `LIVE-UNFILLED` event for the unfilled case.

**In `main.py` (after line 805), using `result["trade_id"]` from the paper insert:**

| Live result | DB action |
|---|---|
| `filled` | `update_trade_execution(trade_id, entry_order_id=…, entry_fill_status='filled', entry_filled_shares=…, entry_price=avg_fill_price, size_usdc=filled_shares*avg_fill_price, clob_token_no=…)`; refund any size delta to bankroll inside the same transaction |
| `partial` | `trim_trade_partial_fill(...)` + store order id / token / status |
| `unfilled` / `skipped` | `void_trade_refund_stake(trade_id, reason)` — the trade never happened; stake returns; row stays for audit with `entry_fill_status='unfilled'` |
| `pending` | store order id + `entry_fill_status='pending'`; reconciler resolves it |

Note: this means in live mode the DB row is created by the paper path and then
**corrected** by the live path. That ordering is deliberate — it preserves the
atomic stake-deduction guarantee of `open_trade_atomic` and keeps paper/live
code unified up to the submission boundary.

**Cleanup (F12):** delete dead lines `live_broker.py:229-231` duplicate
assignment; rewrite the module docstring (lines 13-19) to describe the actual
strategy: *taker at re-quoted ask, poll ≤30s, cancel remainder, reconcile.*

### WI-3 — Exits: sell the token we actually hold (F1, F7)

In the exit-scan live branch (`main.py:1308-1320`):

1. **Token selection:** `token = trade["clob_token_no"] if direction == "NO" else trade["clob_token_yes"]`.
   For legacy live rows where `clob_token_no` is empty, fetch it at exit time
   via `_get_no_token_id` (needs `market_id`, which is on the trade row) and
   persist it.
2. **Share count:** `shares = trade["entry_filled_shares"]` when set; else the
   legacy `size / entry_price`. Round **down** to 2dp (never offer more than we
   hold).
3. **Price:** `exit_val` is already direction-aware upstream
   (`main.py:1240-1241` uses `1 − ask` for NO) — that's the NO token's value, so
   it is the correct limit basis for a SELL on the NO token. Keep
   `min_price = exit_val * 0.95` as the limit, but round **down** to the
   market's tick.

### WI-4 — Exits: verify the fill; never resolve at fictional prices (F5, F6)

Restructure the execute-exit block (`main.py:1294-1339`) for live mode:

1. **Submit & poll:** `sell_position` gains the same poll/cancel loop as WI-2
   (extract a shared `_post_and_poll(order_args, timeout)` helper in
   `live_broker.py`). Exit timeout: `LIVE_EXIT_FILL_TIMEOUT_S` (new config,
   default **60s** — exits tolerate more latency than entries).
2. **Resolve only on confirmed fills**, at the **actual** average fill price:
   `db.resolve_trade(trade_id, None, outcome, avg_fill_price, outcome_source='exit_scan')`,
   with `outcome` recomputed from realized P&L, not the estimate.
   Partial fill: resolve the filled fraction's value — simplest correct
   accounting is `exit_fill_status='partial'`, resolve with
   `exit_price = (filled_shares*avg_price + unfilled_shares*resolution_value)/total`
   … which we can't know yet. **v1 decision:** on partial exit fill, cancel the
   remainder, leave the trade **open** with `size_usdc`/`entry_filled_shares`
   reduced by the sold fraction and the proceeds credited to bankroll
   (mirror of `trim_trade_partial_fill`); the residual position resolves
   normally later. This avoids inventing a blended price.
3. **Unfilled:** cancel the order, set `exit_fill_status='held_to_resolution'`,
   log an `EXIT_UNFILLED` event, and **leave the trade open**. Polymarket
   auto-redeems at resolution (`redeem_positions` docstring,
   `live_broker.py:410-421`), and `--resolve` already settles the DB from the
   actual outcome. Do NOT fall through to `db.resolve_trade` with the estimate.
4. **Kill the entry-price-fallback sell (F6):** in live mode, if no live price
   is available (`price_ok == False`), do not submit a sell at all — the
   `exit_val = entry_price` fallback (`main.py:1297-1298`) becomes paper-only.
   Live behavior: mark `held_to_resolution`, hold.
5. **CLOSING-SOON policy in live (F6):** before submitting a closing-soon exit,
   require a live bid within `LIVE_EXIT_MAX_DISCOUNT` (new config, default
   **0.10**) of `exit_val` and bid-side depth ≥ the position's share count at
   acceptable levels. If the book can't absorb it, hold to resolution. Rationale:
   2h before local midnight a T+0 max-temp outcome is effectively decided;
   selling a winner at a deep discount into a dead book destroys realized edge,
   and resolution pays full value hours later. TAKE-PROFIT and EDGE-REVERSED
   exits keep priority (they fire intraday when books are live) — only the
   time-based exit gets the liquidity gate.
6. Paper mode: zero behavior change. All of the above sits behind
   `db.get_mode() == "live"`.

### WI-5 — Reconciliation daemon job (F4, F9)

New command `main.py --reconcile` (live-only no-op in paper), scheduled in
`daemon.py` `MODEL_RUN_EVENTS`-style as an **hourly** event at **:20 past the
hour** (clear of the :00/:30 scan grid and the 08:15 calibration slot).

Steps, in order:

1. **Stale-order janitor:** `get_open_orders()`; cancel any order older than
   `LIVE_MAX_ORDER_AGE_S` (new config, default **600s** — nothing we post should
   legitimately rest beyond its poll window; 10 min covers daemon crashes
   mid-poll). For each cancelled entry order, find the owning trade by
   `entry_order_id` and apply the WI-2 unfilled/partial correction if its
   status is still `pending`.
2. **Pending-trade sweep:** for DB trades with `entry_fill_status='pending'`,
   query `get_order_status` / `get_clob_fills` and finalize them
   (filled / partial-trim / void-refund) exactly as WI-2 would have.
3. **Position cross-check:** upgrade `sync_positions_to_db` from log-only to:
   - DB-open live trade with `entry_fill_status='filled'` but **no matching
     CLOB position** (match on token id + size within tolerance 5%): telegram
     alert `RECONCILE-MISMATCH`; do not auto-void (could be a data-API lag) —
     alert twice consecutively → flag in `notes` for manual review.
   - CLOB position with **no DB trade**: alert only (manual trades happen).
   - Current matching logic (`live_broker.py:460-481`) matches on
     `conditionId`/market id — switch to **token id + share count**, since a
     YES and NO position in the same market would false-match today.
4. **Bankroll sanity:** compare `db.get_bankroll()` vs
   `get_clob_balance() + get_polymarket_positions_value_usd()`. Drift >
   `LIVE_BANKROLL_DRIFT_ALERT` (new config, default **$5**) → telegram alert.
   Never auto-adjust the DB bankroll; alert only.
5. Log a one-line summary to `scan_log` via `db.log_event("RECONCILE", …)` so
   the dashboard can surface it.

`--sync-positions` stays as the manual verbose version.

### WI-6 — Config additions (`config.py`, live-section)

```python
# ── Live execution integrity ─────────────────────────────────────────────
LIVE_FILL_POLL_S            = 3      # poll interval while waiting for fill
LIVE_FILL_TIMEOUT_S         = 30     # entry: cancel unfilled remainder after this
LIVE_EXIT_FILL_TIMEOUT_S    = 60     # exit: more patience, but still bounded
LIVE_MAX_REQUOTE_SLIP       = 0.02   # abort entry if ask moved this much since scan
LIVE_EXIT_MAX_DISCOUNT      = 0.10   # closing-soon: max discount to fair before holding
LIVE_MAX_ORDER_AGE_S        = 600    # reconciler cancels resting orders older than this
LIVE_BANKROLL_DRIFT_ALERT   = 5.0    # $ divergence DB vs chain before alerting
```

`FILL_TIMEOUT_S` in `live_broker.py` is replaced by the config import.

---

## 4. Edge cases & failure modes

- **Daemon killed mid-poll:** order may fill after we stop watching. Covered by
  WI-5 steps 1–2 (`pending` rows are finalized on the next reconcile). This is
  why `entry_fill_status='pending'` + persisted `entry_order_id` must be written
  **before** polling starts, not after.
- **Fill between timeout and cancel:** handled in WI-2 step 4 (re-check after
  failed cancel; pending if still ambiguous).
- **`get_clob_fills` lag:** average fill price may not be queryable immediately.
  Retry ×3 with 2s backoff; if still absent, use the limit price as the fill
  price (conservative for a taker BUY: actual ≤ limit) and let the reconciler
  refine it.
- **NO token fetch fails at entry** (`_get_no_token_id` → None): already skips
  the live order; with WI-2 the paper row must then be **voided** in live mode,
  not left open (today it stays open with no on-chain position — a silent F9
  case).
- **Same-market YES and NO trades:** token-id-based matching (WI-5 step 3)
  required; market-id matching is ambiguous.
- **Resolution races an unfilled exit:** order cancelled by WI-5, trade open,
  `--resolve` settles from actual weather — correct by construction.
- **Crypto/TSA markets** (`data/polymarket_crypto.py`, `polymarket_tsa.py`):
  same `execute_live_trade` path → they inherit all fixes; verify their market
  dicts carry `market_id` for the NO-token/tick lookups.
- **Voided trade & city-date cap:** voiding refunds stake, so `_open_trades`
  used for the per-city cap (`main.py:766-781`) must reflect the void before the
  next market in the same scan loop — refresh or mutate the in-memory list when
  a void happens.

---

## 5. Testing & validation plan

No test suite exists (per CLAUDE.md), so validation is staged:

1. **Paper invariance:** run `python main.py --scan --paper` and
   `--exit-scan --paper` before/after on a copy of `paper_trades.db`; diff DB
   writes. Must be identical (new columns empty).
2. **Dry-run live:** `--scan --live` with `dry_run` — verify re-quote, tick
   rounding, and slip-abort logic via logs without posting.
3. **Unit-style harness:** small `scripts/test_live_exec.py` (manual, not CI)
   that monkeypatches `py_clob_client` responses to exercise: full fill, partial
   fill, no fill, cancel-race, fills-API lag. Assert DB row corrections and
   bankroll deltas for each.
4. **Micro-live canary:** temporarily set `MAX_TRADE_USDC` low (~$2) in live;
   place 2–3 real entries and force one exit; verify on the Polymarket UI that
   positions/orders match the DB and that the reconciler reports zero mismatches.
5. **One-time historical audit (rollout step):** run the upgraded reconciler
   against the existing live DB; every legacy open live trade gets classified
   (real position / never filled / wrong-token zombie). Manually void/repair
   with a logged script before enabling the daemon schedule.

## 6. Rollout

1. Land WI-1 (schema) + WI-6 (config) — inert.
2. Land WI-2 + WI-3 + WI-4 behind live-mode checks; paper invariance test.
3. Run step-5 historical audit; clean the live book.
4. Land WI-5; add the hourly reconcile to `daemon.py`; watch telegram alerts
   for a week.
5. Micro-live canary (step 4 above) before restoring normal trade sizes.

**Risks:** the poll loop adds up to ~30s per live entry inside the scan loop
(serial over cities) — acceptable at current trade frequency (a handful/day);
if it grows, move polling to a post-scan pass over `pending` rows.
Biggest behavioral change is closing-soon exits holding to resolution: realized
variance shifts from "sell early at a discount" to "binary resolution" — this is
intentional and should be P&L-positive, but watch the first two weeks of
`held_to_resolution` outcomes vs. what the old path would have credited.

## 7. Open questions (decide at implementation time)

1. **FAK instead of GTC+poll for entries?** `py_clob_client` supports
   `OrderType.FAK`; it would collapse WI-2's poll/cancel into one round-trip.
   Chosen GTC+poll for v1 because FAK partial-fill semantics on the CLOB need
   verification first; revisit after the canary.
2. Should EDGE-REVERSED exits cross deeper (price down to `exit_val − 0.05`)
   when the first sell doesn't fill, rather than holding? Edge reversal means we
   actively want out; holding to resolution there is a worse default than for
   closing-soon. Proposed: one repost at a deeper price, then hold.
3. Reconciler auto-void on two consecutive position mismatches vs. alert-only
   forever — start alert-only; promote to auto-void once we trust the matcher.
