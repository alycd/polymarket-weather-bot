"""
Unit tests for broker/correlation_filter.py — covering:
  - _bucket_gap geometry
  - correlation_allows_trade Check 3: NO proximity filter (open_trades + pending_no_buckets)
  - Check 3 does not fire for YES trades
  - Check 1 (region cap) and Check 2 (bucket cap) still work after the refactor
  - Return value: (allowed, reason, conflicting_trade) — conflicting_trade is the blocking
    open trade for cross-scan proximity blocks, None in all other cases
"""
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from broker.correlation_filter import (
    _bucket_gap,
    correlation_allows_trade,
    MIN_NO_BUCKET_GAP_F,
    MIN_NO_BUCKET_GAP_C,
    MAX_BUCKETS_PER_CITY_YES,
    MAX_BUCKETS_PER_CITY_NO,
    REGION_MAX_POSITIONS,
)

DATE = "2026-06-10"

def _no_trade(city, lo, hi, unit="F", target_date=DATE, trade_id=None, size_usdc=15.0,
              entry_price=0.65, market_id="mkt-001"):
    return {
        "trade_id":      trade_id or f"t-{city}-{lo}",
        "market_id":     market_id,
        "city":          city,
        "direction":     "NO",
        "target_date":   target_date,
        "target_date_end": None,
        "bucket_lo":     lo,
        "bucket_hi":     hi,
        "bucket_unit":   unit,
        "size_usdc":     size_usdc,
        "entry_price":   entry_price,
    }

def _yes_trade(city, lo, hi, unit="F", target_date=DATE):
    return {
        "trade_id":      f"t-yes-{city}-{lo}",
        "market_id":     "mkt-yes-001",
        "city":          city,
        "direction":     "YES",
        "target_date":   target_date,
        "target_date_end": None,
        "bucket_lo":     lo,
        "bucket_hi":     hi,
        "bucket_unit":   unit,
        "size_usdc":     15.0,
        "entry_price":   0.35,
    }


class TestBucketGap(unittest.TestCase):

    def test_adjacent_1f_gap(self):
        # [70,71) and [71,72) — gap = 0 (hi1==lo2, half-open so they don't overlap)
        self.assertEqual(_bucket_gap(70, 71, 71, 72), 0.0)

    def test_gap_of_1f(self):
        # [70,71) and [72,73) — gap = 1°F
        self.assertAlmostEqual(_bucket_gap(70, 71, 72, 73), 1.0)

    def test_gap_of_2f(self):
        self.assertAlmostEqual(_bucket_gap(70, 71, 73, 74), 2.0)

    def test_overlap_returns_zero(self):
        self.assertEqual(_bucket_gap(70, 73, 72, 75), 0.0)

    def test_symmetric(self):
        self.assertEqual(_bucket_gap(72, 73, 70, 71), _bucket_gap(70, 71, 72, 73))

    def test_missing_lo_returns_inf(self):
        self.assertEqual(_bucket_gap(None, 71, 72, 73), float("inf"))
        self.assertEqual(_bucket_gap(70, 71, None, 73), float("inf"))

    def test_open_ended_hi(self):
        # [90, inf) and [95, inf) — lo2 >= hi1_eff(inf) is False, lo1 < hi2(inf), lo2 < hi1(inf) → overlap
        self.assertEqual(_bucket_gap(90, None, 95, None), 0.0)

    def test_open_ended_gap(self):
        # [70, 71) and [73, None) — lo2=73 >= hi1=71, gap = 73-71 = 2
        self.assertAlmostEqual(_bucket_gap(70, 71, 73, None), 2.0)


class TestProximityFilter(unittest.TestCase):
    """Check 3: NO proximity blocking and the conflicting_trade return value."""

    def _call(self, city, lo, hi, open_trades, unit="F", pending=None):
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = open_trades
            return correlation_allows_trade(
                city, DATE, direction="NO",
                open_trades=open_trades,
                bucket_lo=lo, bucket_hi=hi, bucket_unit=unit,
                pending_no_buckets=pending,
            )

    # --- blocked: cross-scan (open_trades) ---

    def test_blocks_adjacent_1f_bucket(self):
        # Existing NO on [70,71), new NO on [71,72) — gap=0 < 2°F → blocked
        trades = [_no_trade("New York City", 70, 71)]
        allowed, reason, conflicting = self._call("New York City", 71, 72, trades)
        self.assertFalse(allowed)
        self.assertIn("proximity_cap", reason)

    def test_blocks_1f_gap(self):
        # gap = 1°F < MIN_NO_BUCKET_GAP_F(2) → blocked
        trades = [_no_trade("New York City", 70, 71)]
        allowed, reason, conflicting = self._call("New York City", 72, 73, trades)
        self.assertFalse(allowed)

    def test_blocks_celsius_adjacent(self):
        # [20,21) and [21,22) in °C — gap=0 < 1°C → blocked
        trades = [_no_trade("London", 20, 21, unit="C")]
        allowed, reason, conflicting = self._call("London", 21, 22, trades, unit="C")
        self.assertFalse(allowed)

    # --- cross-scan block returns the conflicting trade dict ---

    def test_cross_scan_block_returns_conflicting_trade(self):
        # The third element must be the exact trade dict that caused the block
        incumbent = _no_trade("New York City", 70, 71, trade_id="t-incumbent")
        trades = [incumbent]
        allowed, reason, conflicting = self._call("New York City", 71, 72, trades)
        self.assertFalse(allowed)
        self.assertIsNotNone(conflicting)
        self.assertEqual(conflicting["trade_id"], "t-incumbent")
        self.assertEqual(conflicting["bucket_lo"], 70)
        self.assertEqual(conflicting["bucket_hi"], 71)

    def test_cross_scan_returns_first_conflicting_trade_when_multiple(self):
        # If two open trades are both too close, returns the first one encountered
        t1 = _no_trade("Chicago", 70, 71, trade_id="t-first")
        t2 = _no_trade("Chicago", 72, 73, trade_id="t-second")
        trades = [t1, t2]
        allowed, reason, conflicting = self._call("Chicago", 71, 72, trades)
        self.assertFalse(allowed)
        self.assertEqual(conflicting["trade_id"], "t-first")

    # --- blocked: same-scan (pending_no_buckets) always returns None ---

    def test_blocks_pending_adjacent(self):
        # Nothing in open_trades, but one in-scan pending NO is adjacent
        pending = [(70.0, 71.0, "F")]
        allowed, reason, conflicting = self._call("Chicago", 71, 72, [], pending=pending)
        self.assertFalse(allowed)
        self.assertIn("in-scan", reason)

    def test_same_scan_block_returns_none_conflicting(self):
        # Same-scan block must NOT expose the trade — there is no dict to return
        pending = [(70.0, 71.0, "F")]
        allowed, reason, conflicting = self._call("Chicago", 71, 72, [], pending=pending)
        self.assertFalse(allowed)
        self.assertIsNone(conflicting)

    def test_same_scan_takes_priority_over_cross_scan(self):
        # If both an open trade AND a pending trade are too close, pending fires first
        # (pending loop runs after open_trades loop, so open trade fires first actually)
        # Regardless, conflicting_trade is from open_trades when that loop hits first
        incumbent = _no_trade("Miami", 70, 71, trade_id="t-open")
        pending = [(72.0, 73.0, "F")]
        allowed, reason, conflicting = self._call("Miami", 71, 72, [incumbent], pending=pending)
        self.assertFalse(allowed)
        # open_trades loop runs first — conflicting is the incumbent
        self.assertIsNotNone(conflicting)
        self.assertEqual(conflicting["trade_id"], "t-open")

    # --- allowed cases all return None as third element ---

    def test_allowed_returns_none_conflicting(self):
        trades = [_no_trade("New York City", 70, 71)]
        allowed, reason, conflicting = self._call("New York City", 73, 74, trades)
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)

    def test_allows_sufficient_f_gap(self):
        # gap = 2°F == MIN_NO_BUCKET_GAP_F — boundary is exclusive (< not <=), so allowed
        trades = [_no_trade("New York City", 70, 71)]
        allowed, _, conflicting = self._call("New York City", 73, 74, trades)
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)

    def test_allows_wide_gap(self):
        trades = [_no_trade("New York City", 70, 71)]
        allowed, _, conflicting = self._call("New York City", 80, 81, trades)
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)

    def test_allows_yes_trade_ignores_proximity(self):
        # YES trade — Check 3 must NOT fire even if bucket is adjacent to an existing NO
        trades = [_no_trade("New York City", 70, 71)]
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, reason, conflicting = correlation_allows_trade(
                "New York City", DATE, direction="YES",
                open_trades=trades,
                bucket_lo=71, bucket_hi=72,
            )
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)

    def test_allows_different_city(self):
        # Adjacent bucket but different city — should not block
        trades = [_no_trade("Chicago", 70, 71)]
        allowed, _, conflicting = self._call("New York City", 71, 72, trades)
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)

    def test_allows_different_date(self):
        # Same city, adjacent bucket, but existing trade is on a different date
        trades = [_no_trade("New York City", 70, 71, target_date="2026-06-09")]
        allowed, _, conflicting = self._call("New York City", 71, 72, trades)
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)

    def test_allows_no_bucket_lo(self):
        # bucket_lo=None → Check 3 skipped entirely
        trades = [_no_trade("New York City", 70, 71)]
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, _, conflicting = correlation_allows_trade(
                "New York City", DATE, direction="NO",
                open_trades=trades,
                bucket_lo=None,
            )
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)


class TestRegionCap(unittest.TestCase):
    """Check 1: region cap — always returns None as conflicting_trade."""

    def _make_trades(self, cities):
        return [{"trade_id": f"t-{c}", "market_id": "m", "city": c, "direction": "YES",
                 "target_date": DATE, "target_date_end": None,
                 "bucket_lo": None, "bucket_hi": None,
                 "size_usdc": 15.0, "entry_price": 0.5} for c in cities]

    def test_blocks_at_cap(self):
        cap = REGION_MAX_POSITIONS["NA_East"]  # 3
        cities = ["New York City", "Chicago", "Atlanta"]
        trades = self._make_trades(cities)
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, reason, conflicting = correlation_allows_trade(
                "Dallas", DATE, direction="YES", open_trades=trades)
        self.assertFalse(allowed)
        self.assertIn("corr_cap", reason)
        self.assertIsNone(conflicting)

    def test_allows_under_cap(self):
        trades = self._make_trades(["New York City", "Chicago"])
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, _, conflicting = correlation_allows_trade(
                "Atlanta", DATE, direction="YES", open_trades=trades)
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)

    def test_region_cap_returns_none_not_conflicting_trade(self):
        # Region cap is a count-based rule — there's no single "conflicting trade" to return
        cap = REGION_MAX_POSITIONS["Europe_W"]
        cities = ["London", "Paris", "Madrid"][:cap]
        trades = self._make_trades(cities)
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, reason, conflicting = correlation_allows_trade(
                "Milan", DATE, direction="YES", open_trades=trades)
        self.assertFalse(allowed)
        self.assertIsNone(conflicting)


class TestBucketCap(unittest.TestCase):
    """Check 2: per-city bucket cap — always returns None as conflicting_trade."""

    def _make_yes_trades(self, city, n):
        return [{"trade_id": f"t-{i}", "market_id": "m", "city": city, "direction": "YES",
                 "target_date": DATE, "target_date_end": None,
                 "bucket_lo": float(i), "bucket_hi": float(i+1),
                 "size_usdc": 15.0, "entry_price": 0.5}
                for i in range(n)]

    def test_blocks_yes_at_cap(self):
        trades = self._make_yes_trades("New York City", MAX_BUCKETS_PER_CITY_YES)
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, reason, conflicting = correlation_allows_trade(
                "New York City", DATE, direction="YES",
                open_trades=trades, bucket_lo=99, bucket_hi=100)
        self.assertFalse(allowed)
        self.assertIn("bucket_cap", reason)
        self.assertIsNone(conflicting)

    def test_allows_no_above_yes_cap(self):
        # NO cap is higher than YES cap; should still allow when YES cap would block
        trades = self._make_yes_trades("New York City", MAX_BUCKETS_PER_CITY_YES)
        for t in trades:
            t["direction"] = "NO"
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            # bucket far away so proximity filter doesn't fire
            allowed, _, conflicting = correlation_allows_trade(
                "New York City", DATE, direction="NO",
                open_trades=trades, bucket_lo=99, bucket_hi=100)
        self.assertTrue(allowed)
        self.assertIsNone(conflicting)

    def test_bucket_cap_returns_none_not_conflicting_trade(self):
        trades = self._make_yes_trades("Chicago", MAX_BUCKETS_PER_CITY_YES)
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, reason, conflicting = correlation_allows_trade(
                "Chicago", DATE, direction="YES",
                open_trades=trades, bucket_lo=99, bucket_hi=100)
        self.assertFalse(allowed)
        self.assertIsNone(conflicting)


if __name__ == "__main__":
    unittest.main()
