"""
Unit tests for broker/correlation_filter.py — covering:
  - _bucket_gap geometry
  - correlation_allows_trade Check 3: NO proximity filter (open_trades + pending_no_buckets)
  - Check 3 does not fire for YES trades
  - Check 1 (region cap) and Check 2 (bucket cap) still work after the refactor
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

def _no_trade(city, lo, hi, unit="F", target_date=DATE):
    return {
        "city": city,
        "direction": "NO",
        "target_date": target_date,
        "target_date_end": None,
        "bucket_lo": lo,
        "bucket_hi": hi,
        "bucket_unit": unit,
    }

def _yes_trade(city, lo, hi, unit="F", target_date=DATE):
    return {
        "city": city,
        "direction": "YES",
        "target_date": target_date,
        "target_date_end": None,
        "bucket_lo": lo,
        "bucket_hi": hi,
        "bucket_unit": unit,
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
    """Check 3: NO proximity blocking."""

    def _allow(self, city, lo, hi, open_trades, unit="F", pending=None):
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = open_trades
            return correlation_allows_trade(
                city, DATE, direction="NO",
                open_trades=open_trades,
                bucket_lo=lo, bucket_hi=hi, bucket_unit=unit,
                pending_no_buckets=pending,
            )

    # --- blocked cases ---

    def test_blocks_adjacent_1f_bucket(self):
        # Existing NO on [70,71), new NO on [71,72) — gap=0 < 2°F → blocked
        trades = [_no_trade("New York City", 70, 71)]
        allowed, reason = self._allow("New York City", 71, 72, trades)
        self.assertFalse(allowed)
        self.assertIn("proximity_cap", reason)

    def test_blocks_1f_gap(self):
        # gap = 1°F < MIN_NO_BUCKET_GAP_F(2) → blocked
        trades = [_no_trade("New York City", 70, 71)]
        allowed, reason = self._allow("New York City", 72, 73, trades)
        self.assertFalse(allowed)

    def test_blocks_pending_adjacent(self):
        # Nothing in open_trades, but one in-scan pending NO is adjacent
        pending = [(70.0, 71.0, "F")]
        allowed, reason = self._allow("Chicago", 71, 72, [], pending=pending)
        self.assertFalse(allowed)
        self.assertIn("in-scan", reason)

    def test_blocks_celsius_adjacent(self):
        # [20,21) and [21,22) in °C — gap=0 < 1°C → blocked
        trades = [_no_trade("London", 20, 21, unit="C")]
        allowed, reason = self._allow("London", 21, 22, trades, unit="C")
        self.assertFalse(allowed)

    # --- allowed cases ---

    def test_allows_sufficient_f_gap(self):
        # gap = 2°F == MIN_NO_BUCKET_GAP_F — boundary is exclusive (< not <=), so allowed
        trades = [_no_trade("New York City", 70, 71)]
        allowed, _ = self._allow("New York City", 73, 74, trades)
        self.assertTrue(allowed)

    def test_allows_wide_gap(self):
        trades = [_no_trade("New York City", 70, 71)]
        allowed, _ = self._allow("New York City", 80, 81, trades)
        self.assertTrue(allowed)

    def test_allows_yes_trade_ignores_proximity(self):
        # YES trade — Check 3 must NOT fire even if bucket is adjacent to an existing NO
        trades = [_no_trade("New York City", 70, 71)]
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, reason = correlation_allows_trade(
                "New York City", DATE, direction="YES",
                open_trades=trades,
                bucket_lo=71, bucket_hi=72,
            )
        self.assertTrue(allowed)

    def test_allows_different_city(self):
        # Adjacent bucket but different city — should not block
        trades = [_no_trade("Chicago", 70, 71)]
        allowed, _ = self._allow("New York City", 71, 72, trades)
        self.assertTrue(allowed)

    def test_allows_different_date(self):
        # Same city, adjacent bucket, but existing trade is on a different date
        trades = [_no_trade("New York City", 70, 71, target_date="2026-06-09")]
        allowed, _ = self._allow("New York City", 71, 72, trades)
        self.assertTrue(allowed)

    def test_allows_no_bucket_lo(self):
        # bucket_lo=None → Check 3 skipped entirely
        trades = [_no_trade("New York City", 70, 71)]
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, _ = correlation_allows_trade(
                "New York City", DATE, direction="NO",
                open_trades=trades,
                bucket_lo=None,
            )
        self.assertTrue(allowed)


class TestRegionCap(unittest.TestCase):
    """Check 1: region cap still works."""

    def _make_trades(self, cities):
        return [{"city": c, "direction": "YES", "target_date": DATE,
                 "target_date_end": None, "bucket_lo": None, "bucket_hi": None} for c in cities]

    def test_blocks_at_cap(self):
        cap = REGION_MAX_POSITIONS["NA_East"]  # 3
        cities = ["New York City", "Chicago", "Atlanta"]  # 3 different cities at cap
        trades = self._make_trades(cities)
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, reason = correlation_allows_trade(
                "Dallas", DATE, direction="YES", open_trades=trades)
        self.assertFalse(allowed)
        self.assertIn("corr_cap", reason)

    def test_allows_under_cap(self):
        trades = self._make_trades(["New York City", "Chicago"])
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, _ = correlation_allows_trade(
                "Atlanta", DATE, direction="YES", open_trades=trades)
        self.assertTrue(allowed)


class TestBucketCap(unittest.TestCase):
    """Check 2: per-city bucket cap."""

    def _make_yes_trades(self, city, n):
        return [{"city": city, "direction": "YES", "target_date": DATE,
                 "target_date_end": None, "bucket_lo": float(i), "bucket_hi": float(i+1)}
                for i in range(n)]

    def test_blocks_yes_at_cap(self):
        trades = self._make_yes_trades("New York City", MAX_BUCKETS_PER_CITY_YES)
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            allowed, reason = correlation_allows_trade(
                "New York City", DATE, direction="YES",
                open_trades=trades, bucket_lo=99, bucket_hi=100)
        self.assertFalse(allowed)
        self.assertIn("bucket_cap", reason)

    def test_allows_no_above_yes_cap(self):
        # NO cap is higher than YES cap; should still allow when YES cap would block
        trades = self._make_yes_trades("New York City", MAX_BUCKETS_PER_CITY_YES)
        # Convert all to NO direction for the NO cap test
        for t in trades:
            t["direction"] = "NO"
        with patch("broker.correlation_filter.db") as mock_db:
            mock_db.get_open_trades.return_value = trades
            # bucket far away so proximity filter doesn't fire
            allowed, _ = correlation_allows_trade(
                "New York City", DATE, direction="NO",
                open_trades=trades, bucket_lo=99, bucket_hi=100)
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
