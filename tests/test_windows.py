import unittest

from snprice.windows import bounds, emitting_blocks, sample_blocks

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


class EmittingBlocksTest(unittest.TestCase):
    """Blocks of a window (lo, hi] in which a subnet emitted alpha."""

    def test_subnet_that_emitted_since_before_the_window(self):
        self.assertEqual(emitting_blocks(1000, 2000, first_emission=500), 1000)

    def test_emissions_that_started_inside_the_window_count_from_their_first_block(self):
        self.assertEqual(emitting_blocks(1000, 2000, first_emission=1901), 100)
        self.assertEqual(emitting_blocks(1000, 2000, first_emission=2000), 1)

    def test_first_block_of_the_window(self):
        self.assertEqual(emitting_blocks(1000, 2000, first_emission=1001), 1000)

    def test_emissions_that_started_after_the_window(self):
        self.assertEqual(emitting_blocks(1000, 2000, first_emission=2001), 0)

    def test_subnet_that_has_not_started_emissions(self):
        self.assertEqual(emitting_blocks(1000, 2000, first_emission=None), 0)


if __name__ == "__main__":
    unittest.main()
