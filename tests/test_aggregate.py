import unittest

from snprice.aggregate import window_summary

DAY_OF = {100: "2026-09-01", 200: "2026-09-02"}


def sample(block, price, burn, enabled, tao_em, reg_cost):
    # values arrive as text, the way read_table returns them
    return {"block": str(block), "price_tao": price, "miner_burned": burn, "emission_enabled": enabled,
            "tao_in_emission": tao_em, "reg_cost_tao": reg_cost}


def paid(block, coldkey, hotkey, weight, owner="0", ip=None):
    return {"block": str(block), "coldkey": coldkey, "hotkey": hotkey, "weight": weight, "owner": owner, "ip": ip}


SAMPLES = [sample(100, "0.01", "0.0", "1", "0.01", "0.2"), sample(200, "0.03", "0.5", "0", "0", None)]
ROWS = [paid(100, "A", "h1", "0.6", ip="1.1.1.1"), paid(100, "B", "h3", "0.4", ip="2.2.2.2"),
        paid(200, "OWN", "h0", "0.5", owner="1"), paid(200, "A", "h2", "0.5")]


class WindowSummaryTest(unittest.TestCase):
    def test_pool_and_burn_statistics(self):
        out = window_summary(SAMPLES, ROWS, DAY_OF)
        self.assertEqual(out["samples_observed"], 2)
        self.assertEqual(out["window_days_observed"], 2)
        self.assertAlmostEqual(out["price_tao_avg"], 0.02)
        self.assertAlmostEqual(out["burn_mean"], 0.25)
        self.assertAlmostEqual(out["burn_time_share_ge50"], 0.5)
        self.assertAlmostEqual(out["emission_enabled_days_share"], 0.5)
        self.assertAlmostEqual(out["tao_emission_on_share"], 0.5)
        self.assertAlmostEqual(out["reg_cost_tao_mean"], 0.2)
        self.assertEqual(out["flag_full_burn"], 0)

    def test_miner_counts_and_concentration(self):
        out = window_summary(SAMPLES, ROWS, DAY_OF)
        self.assertEqual(out["miners_paid_hotkeys"], 3)
        self.assertEqual(out["miners_paid_coldkeys"], 2)
        self.assertEqual(out["miner_paid_days"], 2)
        self.assertAlmostEqual(out["shares"]["A"], 1.1 / 1.5)
        self.assertAlmostEqual(out["shares"]["B"], 0.4 / 1.5)
        self.assertAlmostEqual(out["miner_hhi_coldkey"], (1.1 / 1.5) ** 2 + (0.4 / 1.5) ** 2)
        self.assertAlmostEqual(out["miner_top1_share"], 1.1 / 1.5)
        self.assertAlmostEqual(out["owner_incentive_share"], 0.25)
        self.assertEqual(out["flag_no_miner_paid"], 0)

    def test_ip_count_is_reported_when_at_least_half_of_the_hotkeys_publish_one(self):
        out = window_summary(SAMPLES, ROWS, DAY_OF)
        self.assertAlmostEqual(out["miners_ip_coverage"], 2 / 3)
        self.assertEqual(out["miners_distinct_ips"], 2)

    def test_ip_count_is_missing_below_half_coverage(self):
        rows = [paid(100, "A", "h1", "0.5", ip="1.1.1.1"), paid(100, "B", "h2", "0.3"), paid(100, "C", "h3", "0.2")]
        out = window_summary(SAMPLES[:1], rows, DAY_OF)
        self.assertAlmostEqual(out["miners_ip_coverage"], 1 / 3)
        self.assertIsNone(out["miners_distinct_ips"])

    def test_subnet_not_yet_registered_in_the_window_has_missing_values_not_zeros(self):
        out = window_summary([], [], DAY_OF)
        self.assertEqual(out["samples_observed"], 0)
        self.assertEqual(out["window_days_observed"], 0)
        self.assertEqual(out["shares"], {})
        for key, value in out.items():
            if key not in ("samples_observed", "window_days_observed", "shares"):
                self.assertIsNone(value, key)

    def test_observed_window_in_which_nobody_was_paid(self):
        samples = [sample(100, "0.01", "1.0", "1", "0.01", "0.2"), sample(200, "0.01", "1.0", "1", "0.01", "0.2")]
        rows = [paid(100, "OWN", "h0", "1.0", owner="1"), paid(200, "OWN", "h0", "1.0", owner="1")]
        out = window_summary(samples, rows, DAY_OF)
        self.assertEqual(out["miners_paid_hotkeys"], 0)
        self.assertEqual(out["miners_paid_coldkeys"], 0)
        self.assertEqual(out["miner_paid_days"], 0)
        self.assertIsNone(out["miner_hhi_coldkey"])
        self.assertIsNone(out["miner_top1_share"])
        self.assertIsNone(out["miners_ip_coverage"])
        self.assertEqual(out["flag_no_miner_paid"], 1)
        self.assertEqual(out["flag_full_burn"], 1)
        self.assertAlmostEqual(out["owner_incentive_share"], 1.0)

    def test_wallet_without_coldkey_is_identified_by_its_hotkey(self):
        out = window_summary(SAMPLES[:1], [paid(100, None, "h9", "1.0")], DAY_OF)
        self.assertEqual(list(out["shares"]), ["h9"])


if __name__ == "__main__":
    unittest.main()
