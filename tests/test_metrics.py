import random
import unittest

from snprice.metrics import (
    hhi_from_amounts,
    holder_bounds,
    mech_weighted,
    pooled_shares,
    spaced_count,
    uid_weights,
)


class HhiTest(unittest.TestCase):
    def test_equal_split_of_four_gives_one_quarter(self):
        self.assertAlmostEqual(hhi_from_amounts([5, 5, 5, 5]), 0.25)

    def test_single_holder_gives_one(self):
        self.assertAlmostEqual(hhi_from_amounts([7.0]), 1.0)

    def test_zero_total_is_missing_not_zero(self):
        self.assertIsNone(hhi_from_amounts([]))
        self.assertIsNone(hhi_from_amounts([0.0, 0.0]))


class MechWeightedTest(unittest.TestCase):
    def test_single_mechanism_passes_through(self):
        self.assertAlmostEqual(mech_weighted([0.4], [1.0]), 0.4)

    def test_split_zero_one_uses_only_second_mechanism(self):
        self.assertAlmostEqual(mech_weighted([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertAlmostEqual(mech_weighted([0.0, 0.25], [0.0, 1.0]), 0.25)

    def test_split_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            mech_weighted([0.5, 0.5], [0.5, 0.2])

    def test_lengths_must_match(self):
        with self.assertRaises(ValueError):
            mech_weighted([0.5], [0.5, 0.5])


class UidWeightsTest(unittest.TestCase):
    def test_single_mechanism_normalises_the_vector(self):
        self.assertEqual(uid_weights([[0, 30, 10]], None), {1: 0.75, 2: 0.25})

    def test_zero_incentive_uids_are_left_out(self):
        self.assertNotIn(0, uid_weights([[0, 5]], [65535]))

    def test_split_zero_one_pays_only_the_second_mechanism(self):
        out = uid_weights([[65535, 0, 0], [0, 100, 300]], [0, 65535])
        self.assertEqual(out, {1: 0.25, 2: 0.75})

    def test_two_mechanisms_are_weighted_by_the_split(self):
        out = uid_weights([[10, 0], [0, 10]], [3, 1])
        self.assertAlmostEqual(out[0], 0.75)
        self.assertAlmostEqual(out[1], 0.25)
        self.assertAlmostEqual(sum(out.values()), 1.0)

    def test_mechanism_that_paid_nobody_is_ignored(self):
        out = uid_weights([[0, 0], [4, 12]], [1, 1])
        self.assertEqual(out, {0: 0.25, 1: 0.75})

    def test_missing_second_vector(self):
        self.assertEqual(uid_weights([[1, 1], None], [1, 1]), {0: 0.5, 1: 0.5})

    def test_nothing_paid(self):
        self.assertEqual(uid_weights([[0, 0], None], None), {})
        self.assertEqual(uid_weights([None, None], None), {})

    def test_vectors_of_different_length(self):
        out = uid_weights([[1, 1], [0, 0, 2]], [1, 1])
        self.assertAlmostEqual(out[0], 0.25)
        self.assertAlmostEqual(out[2], 0.5)


def row(sample, wallet, value, owner=False):
    return {"sample": sample, "wallet": wallet, "value": value, "owner": owner}


class PooledSharesTest(unittest.TestCase):
    def test_shares_pool_over_samples_instead_of_averaging(self):
        # day 1: nothing burned, A takes all. day 2: 90% burned, B takes the rest.
        rows = [
            row(1, "A", 1.0),
            row(2, "B", 0.1),
            row(2, "OWNER", 0.9, owner=True),
        ]
        out = pooled_shares(rows)
        # paid mass: A 1.0, B 0.1 -> A 10/11, B 1/11 (a per-day average would give 1/2 each)
        self.assertAlmostEqual(out["shares"]["A"], 1.0 / 1.1)
        self.assertAlmostEqual(out["shares"]["B"], 0.1 / 1.1)
        self.assertEqual(out["paid_samples"], 2)
        self.assertEqual(out["samples"], 2)

    def test_values_are_normalised_within_each_sample(self):
        # raw incentive scales differ between samples; each sample must weigh by its own total
        rows = [row(1, "A", 30), row(1, "B", 10), row(2, "A", 1), row(2, "B", 3)]
        out = pooled_shares(rows)
        self.assertAlmostEqual(out["shares"]["A"], (0.75 + 0.25) / 2)
        self.assertAlmostEqual(out["shares"]["B"], (0.25 + 0.75) / 2)

    def test_owner_rows_are_excluded_and_reported(self):
        rows = [row(1, "A", 0.5), row(1, "OWNER", 0.5, owner=True)]
        out = pooled_shares(rows)
        self.assertEqual(set(out["shares"]), {"A"})
        self.assertAlmostEqual(out["shares"]["A"], 1.0)
        self.assertAlmostEqual(out["owner_share"], 0.5)

    def test_nobody_paid_gives_empty_shares_and_no_owner_division_error(self):
        rows = [row(1, "OWNER", 1.0, owner=True), row(2, "OWNER", 1.0, owner=True)]
        out = pooled_shares(rows)
        self.assertEqual(out["shares"], {})
        self.assertEqual(out["paid_samples"], 0)
        self.assertAlmostEqual(out["owner_share"], 1.0)

    def test_samples_without_any_incentive_are_ignored(self):
        rows = [row(1, "A", 0.0), row(2, "A", 2.0)]
        out = pooled_shares(rows)
        self.assertAlmostEqual(out["shares"]["A"], 1.0)
        self.assertEqual(out["samples"], 1)

    def test_no_rows_at_all(self):
        out = pooled_shares([])
        self.assertEqual(out["shares"], {})
        self.assertIsNone(out["owner_share"])

    def test_same_wallet_with_two_uids_in_one_sample_is_summed(self):
        rows = [row(1, "A", 1), row(1, "A", 1), row(1, "B", 2)]
        out = pooled_shares(rows)
        self.assertAlmostEqual(out["shares"]["A"], 0.5)


class HolderBoundsTest(unittest.TestCase):
    def test_complete_information_has_zero_width(self):
        out = holder_bounds([60, 30, 10], total=100)
        self.assertAlmostEqual(out["hhi_lower"], 0.36 + 0.09 + 0.01)
        self.assertAlmostEqual(out["hhi_upper"], out["hhi_lower"])
        self.assertAlmostEqual(out["untraced_share"], 0.0)
        self.assertAlmostEqual(out["top10_lower"], 1.0)

    def test_untraced_mass_widens_the_bounds(self):
        out = holder_bounds([50, 20], total=100)
        self.assertAlmostEqual(out["untraced_share"], 0.30)
        self.assertAlmostEqual(out["hhi_lower"], 0.25 + 0.04)
        # worst case: the whole remainder belongs to the largest wallet
        self.assertAlmostEqual(out["hhi_upper"], 0.64 + 0.04)
        self.assertAlmostEqual(out["top10_lower"], 0.70)
        self.assertAlmostEqual(out["top10_upper"], 1.0)

    def test_true_values_always_inside_bounds_for_random_truncations(self):
        rng = random.Random(42)
        for _ in range(200):
            n = rng.randint(1, 60)
            wallets = sorted((rng.paretovariate(1.2) for _ in range(n)), reverse=True)
            total = sum(wallets)
            true_hhi = sum((w / total) ** 2 for w in wallets)
            true_top10 = sum(wallets[:10]) / total
            keep = rng.randint(1, n)
            out = holder_bounds(wallets[:keep], total=total)
            self.assertLessEqual(out["hhi_lower"], true_hhi + 1e-12)
            self.assertGreaterEqual(out["hhi_upper"], true_hhi - 1e-12)
            self.assertLessEqual(out["top10_lower"], true_top10 + 1e-12)
            self.assertGreaterEqual(out["top10_upper"], true_top10 - 1e-12)

    def test_zero_total_is_missing(self):
        out = holder_bounds([], total=0)
        self.assertIsNone(out["hhi_lower"])
        self.assertIsNone(out["top10_lower"])

    def test_known_mass_slightly_above_total_is_clamped(self):
        # balances and the total can be read a few blocks apart
        out = holder_bounds([60, 41], total=100)
        self.assertAlmostEqual(out["untraced_share"], 0.0)


class SpacedCountTest(unittest.TestCase):
    DAY = 86400

    def test_no_events(self):
        self.assertEqual(spaced_count([], gap=14 * self.DAY), 0)

    def test_events_far_apart_all_count(self):
        self.assertEqual(spaced_count([0, 15 * self.DAY, 40 * self.DAY], gap=14 * self.DAY), 3)

    def test_event_soon_after_a_counted_one_is_the_same_event(self):
        # a live stream and its edited re-upload six days later
        self.assertEqual(spaced_count([0, 6 * self.DAY], gap=14 * self.DAY), 1)

    def test_gap_is_measured_from_the_last_counted_event(self):
        self.assertEqual(spaced_count([0, 10 * self.DAY, 20 * self.DAY], gap=14 * self.DAY), 2)
        self.assertEqual(spaced_count([0, 6 * self.DAY, 13 * self.DAY], gap=14 * self.DAY), 1)

    def test_order_of_input_does_not_matter(self):
        self.assertEqual(spaced_count([20 * self.DAY, 0, 10 * self.DAY], gap=14 * self.DAY), 2)


if __name__ == "__main__":
    unittest.main()
