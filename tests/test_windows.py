import unittest

from snprice.windows import bounds, sample_blocks

CFG = {"t_block": 9184186, "grid_blocks": 900, "blocks_per_day": 7200, "window_days": 30, "lag_days": 30}
T = CFG["t_block"]


class WindowsTest(unittest.TestCase):
    def test_window_has_eight_samples_a_day_ending_at_t(self):
        w = sample_blocks(CFG, "window")
        self.assertEqual(len(w), 240)
        self.assertEqual(w[-1], T)
        self.assertEqual(w[0], T - 239 * 900)
        self.assertEqual(w, sorted(w))

    def test_lag_window_ends_exactly_30_days_of_blocks_before_t(self):
        lag = sample_blocks(CFG, "lag")
        self.assertEqual(len(lag), 240)
        self.assertEqual(lag[-1], T - 216000)
        self.assertEqual(lag[0], T - 216000 - 239 * 900)

    def test_windows_do_not_overlap_and_all_is_their_union(self):
        w, lag = sample_blocks(CFG, "window"), sample_blocks(CFG, "lag")
        self.assertEqual(set(w) & set(lag), set())
        self.assertEqual(sample_blocks(CFG, "all"), lag + w)

    def test_bounds_are_half_open_block_ranges(self):
        self.assertEqual(bounds(CFG, "window"), (T - 216000, T))
        self.assertEqual(bounds(CFG, "lag"), (T - 432000, T - 216000))
        lo, hi = bounds(CFG, "window")
        self.assertTrue(all(lo < b <= hi for b in sample_blocks(CFG, "window")))
        lo, hi = bounds(CFG, "lag")
        self.assertTrue(all(lo < b <= hi for b in sample_blocks(CFG, "lag")))

    def test_longer_window(self):
        self.assertEqual(bounds(CFG, "window", days=90), (T - 648000, T))

    def test_unknown_window_name(self):
        with self.assertRaises(ValueError):
            sample_blocks(CFG, "future")


if __name__ == "__main__":
    unittest.main()
