import math
import unittest

from snprice.panel import forward_outcomes, last_seen, tiling_problems


def row(uid, price, **more):
    return {"subnet_uid": uid, "netuid": uid.split("-")[0], "price_tao": price, **more}


class ForwardOutcomesTest(unittest.TestCase):
    def test_subnet_that_is_still_there_gets_the_price_change(self):
        out = forward_outcomes([row("64-100", "0.07")], [row("64-100", "0.14")], last={})
        self.assertEqual(out["64-100"]["evicted_fwd30"], 0)
        self.assertAlmostEqual(out["64-100"]["price_tao_fwd30"], 0.14)
        self.assertAlmostEqual(out["64-100"]["logret_fwd30"], math.log(2))

    def test_subnet_whose_netuid_went_to_another_registration_was_evicted(self):
        later = [row("82-9155260", "0.004")]              # the same netuid, registered anew
        out = forward_outcomes([row("82-8026517", "0.01")], later, last={})
        self.assertEqual(out["82-8026517"]["evicted_fwd30"], 1)
        self.assertIsNone(out["82-8026517"]["price_tao_fwd30"])
        self.assertIsNone(out["82-8026517"]["logret_fwd30"])

    def test_evicted_subnet_keeps_its_last_observed_price(self):
        last = {"82-8026517": {"block": 9300000, "price_tao": 0.005}}
        out = forward_outcomes([row("82-8026517", "0.01")], [row("82-9155260", "0.004")], last=last)["82-8026517"]
        self.assertAlmostEqual(out["price_tao_last"], 0.005)
        self.assertAlmostEqual(out["logret_to_last"], math.log(0.5))
        self.assertEqual(out["last_block"], 9300000)

    def test_surviving_subnet_has_its_last_price_at_the_later_snapshot(self):
        last = {"64-100": {"block": 9400186, "price_tao": 0.14}}
        out = forward_outcomes([row("64-100", "0.07")], [row("64-100", "0.14")], last=last)["64-100"]
        self.assertAlmostEqual(out["logret_to_last"], out["logret_fwd30"])

    def test_missing_price_gives_missing_change(self):
        out = forward_outcomes([row("5-1", "")], [row("5-1", "0.1")], last={})
        self.assertIsNone(out["5-1"]["logret_fwd30"])


class LastSeenTest(unittest.TestCase):
    """The last sample of each registration in a grid of chain samples."""

    GRID = [
        {"block": "100", "netuid": "82", "registered_block": "50", "price_tao": "0.010"},
        {"block": "200", "netuid": "82", "registered_block": "50", "price_tao": "0.008"},
        {"block": "300", "netuid": "82", "registered_block": "250", "price_tao": "0.004"},
        {"block": "300", "netuid": "64", "registered_block": "10", "price_tao": "0.07"},
    ]

    def test_last_sample_per_registration(self):
        out = last_seen(self.GRID)
        self.assertEqual(out["82-50"], {"block": 200, "price_tao": 0.008})
        self.assertEqual(out["82-250"], {"block": 300, "price_tao": 0.004})
        self.assertEqual(out["64-10"], {"block": 300, "price_tao": 0.07})


class TilingTest(unittest.TestCase):
    """The lagged columns of a wave must repeat the values of the wave before it."""

    PAIRS = [("price_tao", "price_tao_lag30"), ("burn_mean_30d", "burn_mean_lag30")]

    def test_equal_values_give_no_problem(self):
        a = [row("64-100", "0.07", burn_mean_30d="0.25")]
        b = [row("64-100", "0.14", price_tao_lag30="0.07", burn_mean_lag30="0.25")]
        self.assertEqual(tiling_problems(a, b, self.PAIRS), [])

    def test_different_value_is_reported_with_both_numbers(self):
        a = [row("64-100", "0.07", burn_mean_30d="0.25")]
        b = [row("64-100", "0.14", price_tao_lag30="0.08", burn_mean_lag30="0.25")]
        self.assertEqual(tiling_problems(a, b, self.PAIRS), [("64-100", "price_tao", "0.07", "price_tao_lag30", "0.08")])

    def test_missing_on_one_side_only_is_a_problem(self):
        a = [row("64-100", "0.07", burn_mean_30d="")]
        b = [row("64-100", "0.14", price_tao_lag30="0.07", burn_mean_lag30="0.25")]
        self.assertEqual(len(tiling_problems(a, b, self.PAIRS)), 1)

    def test_missing_on_both_sides_is_fine(self):
        a = [row("64-100", "0.07", burn_mean_30d="")]
        b = [row("64-100", "0.14", price_tao_lag30="0.07", burn_mean_lag30="")]
        self.assertEqual(tiling_problems(a, b, self.PAIRS), [])

    def test_subnets_registered_anew_are_not_compared(self):
        a = [row("82-8026517", "0.01", burn_mean_30d="0")]
        b = [row("82-9155260", "0.004", price_tao_lag30="", burn_mean_lag30="")]
        self.assertEqual(tiling_problems(a, b, self.PAIRS), [])


if __name__ == "__main__":
    unittest.main()
