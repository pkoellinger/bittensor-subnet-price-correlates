import unittest

from snprice.aggregate import emissions_paid_after, measured_blocks, window_summary

DAY_OF = {100: "2026-09-01", 200: "2026-09-02"}
LONG_AGO = -10 ** 6      # the subnet has paid emissions since long before the window


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
        out = window_summary(SAMPLES, ROWS, DAY_OF, LONG_AGO)
        self.assertEqual(out["samples_observed"], 2)
        self.assertEqual(out["window_days_observed"], 2)
        self.assertAlmostEqual(out["price_tao_avg"], 0.02)
        self.assertAlmostEqual(out["burn_mean"], 0.25)
        self.assertAlmostEqual(out["burn_time_share_ge50"], 0.5)
        self.assertAlmostEqual(out["emission_flag_on_share"], 0.5)
        self.assertAlmostEqual(out["tao_emission_on_share"], 0.5)
        self.assertAlmostEqual(out["reg_cost_tao_mean"], 0.2)
        self.assertEqual(out["flag_full_burn"], 0)

    def test_miner_counts_and_concentration(self):
        out = window_summary(SAMPLES, ROWS, DAY_OF, LONG_AGO)
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
        out = window_summary(SAMPLES, ROWS, DAY_OF, LONG_AGO)
        self.assertAlmostEqual(out["miners_ip_coverage"], 2 / 3)
        self.assertEqual(out["miners_distinct_ips"], 2)

    def test_ip_count_is_missing_below_half_coverage(self):
        rows = [paid(100, "A", "h1", "0.5", ip="1.1.1.1"), paid(100, "B", "h2", "0.3"), paid(100, "C", "h3", "0.2")]
        out = window_summary(SAMPLES[:1], rows, DAY_OF, LONG_AGO)
        self.assertAlmostEqual(out["miners_ip_coverage"], 1 / 3)
        self.assertIsNone(out["miners_distinct_ips"])

    def test_subnet_not_yet_registered_in_the_window_has_missing_values_not_zeros(self):
        out = window_summary([], [], DAY_OF, LONG_AGO)
        self.assertEqual(out["samples_observed"], 0)
        self.assertEqual(out["window_days_observed"], 0)
        self.assertEqual(out["shares"], {})
        for key, value in out.items():
            if key not in ("samples_observed", "window_days_observed", "shares"):
                self.assertIsNone(value, key)

    def test_observed_window_in_which_nobody_was_paid(self):
        samples = [sample(100, "0.01", "1.0", "1", "0.01", "0.2"), sample(200, "0.01", "1.0", "1", "0.01", "0.2")]
        rows = [paid(100, "OWN", "h0", "1.0", owner="1"), paid(200, "OWN", "h0", "1.0", owner="1")]
        out = window_summary(samples, rows, DAY_OF, LONG_AGO)
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
        out = window_summary(SAMPLES[:1], [paid(100, None, "h9", "1.0")], DAY_OF, LONG_AGO)
        self.assertEqual(list(out["shares"]), ["h9"])


class EmissionStartTest(unittest.TestCase):
    """Until a subnet has paid emissions, the chain stores a burn of 0 by default: not a measurement."""

    OWNER_ONLY = [paid(100, "OWN", "h0", "1.0", owner="1"), paid(200, "OWN", "h0", "1.0", owner="1")]

    def test_emissions_are_paid_at_the_end_of_a_tempo(self):
        # start at block 1000, tempo 360: by block 1360 the first payout has certainly happened
        self.assertEqual(emissions_paid_after(1000, 360), 1360)

    def test_subnet_that_has_not_started_emissions_never_paid(self):
        self.assertIsNone(emissions_paid_after(None, 360))

    def test_measured_blocks_need_a_payout_and_some_incentive(self):
        rows = [paid(100, "A", "h1", "1.0"), paid(200, "OWN", "h0", "1.0", owner="1")]
        self.assertEqual(measured_blocks(rows, LONG_AGO), {100, 200})
        self.assertEqual(measured_blocks(rows, 100), {200})          # block 100 is not after block 100
        self.assertEqual(measured_blocks(rows, 250), set())
        self.assertEqual(measured_blocks(rows, None), set())

    def test_burn_is_measured_only_once_emissions_are_paid(self):
        samples = [sample(100, "0.01", "0.0", "0", "0", "0.2"), sample(200, "0.03", "1.0", "1", "0", "0.2")]
        out = window_summary(samples, self.OWNER_ONLY, DAY_OF, 150)
        self.assertAlmostEqual(out["burn_mean"], 1.0)
        self.assertAlmostEqual(out["burn_time_share_ge50"], 1.0)
        self.assertEqual(out["flag_full_burn"], 1)

    def test_price_and_emission_shares_use_every_sample_since_registration(self):
        samples = [sample(100, "0.01", "0.0", "0", "0", "0.2"), sample(200, "0.03", "1.0", "1", "0.5", "0.4")]
        out = window_summary(samples, self.OWNER_ONLY, DAY_OF, 150)
        self.assertEqual(out["samples_observed"], 2)
        self.assertAlmostEqual(out["price_tao_avg"], 0.02)
        self.assertAlmostEqual(out["emission_flag_on_share"], 0.5)
        self.assertAlmostEqual(out["tao_emission_on_share"], 0.5)
        self.assertAlmostEqual(out["reg_cost_tao_mean"], 0.3)

    def test_subnet_that_never_paid_emissions_has_no_burn(self):
        samples = [sample(100, "0.01", "0.0", "1", "0", "0.2"), sample(200, "0.03", "0.0", "1", "0", "0.2")]
        out = window_summary(samples, self.OWNER_ONLY, DAY_OF, None)
        self.assertIsNone(out["burn_mean"])
        self.assertIsNone(out["burn_time_share_ge50"])
        self.assertEqual(out["flag_full_burn"], 0)
        self.assertEqual(out["flag_no_miner_paid"], 1)
        self.assertIsNone(out["owner_incentive_share"])

    def test_incentive_held_before_emissions_are_paid_pays_nobody(self):
        rows = [paid(100, "A", "h1", "1.0", ip="1.1.1.1"), paid(200, "B", "h2", "1.0")]
        out = window_summary(SAMPLES, rows, DAY_OF, 150)
        self.assertEqual(list(out["shares"]), ["B"])
        self.assertEqual(out["miners_paid_hotkeys"], 1)
        self.assertEqual(out["miner_paid_days"], 1)
        self.assertAlmostEqual(out["miners_ip_coverage"], 0.0)

    def test_sample_at_which_no_uid_holds_incentive_has_no_burn(self):
        # the chain writes 0 when there is no incentive to divide
        samples = [sample(100, "0.01", "0.0", "1", "0", "0.2"), sample(200, "0.01", "0.8", "1", "0", "0.2")]
        rows = [paid(200, "OWN", "h0", "0.8", owner="1"), paid(200, "A", "h1", "0.2")]
        out = window_summary(samples, rows, DAY_OF, LONG_AGO)
        self.assertAlmostEqual(out["burn_mean"], 0.8)
        self.assertAlmostEqual(out["burn_time_share_ge50"], 1.0)


if __name__ == "__main__":
    unittest.main()
