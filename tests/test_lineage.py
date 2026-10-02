import unittest

from snprice.lineage import cluster, lineage_summary, material_funders


def f(frm, amt=1.0, blk=100):
    return {"frm": frm, "amt": amt, "blk": blk}


class MaterialFundersTest(unittest.TestCase):
    def tx(self, frm, to, amount, block):
        return {"from": frm, "to": to, "amount": amount, "block": block}

    def test_keeps_transfers_at_or_above_threshold_before_registration(self):
        rows = [self.tx("F", "A", 0.2, 90), self.tx("G", "A", 0.19, 90)]
        out = material_funders(rows, "A", reg_block=100, threshold=0.2)
        self.assertEqual([r["frm"] for r in out], ["F"])

    def test_transfers_at_or_after_registration_are_ignored(self):
        rows = [self.tx("F", "A", 5, 100), self.tx("G", "A", 5, 101), self.tx("H", "A", 5, 99)]
        out = material_funders(rows, "A", reg_block=100, threshold=0.2)
        self.assertEqual([r["frm"] for r in out], ["H"])

    def test_self_transfers_and_other_recipients_are_ignored(self):
        rows = [self.tx("A", "A", 5, 50), self.tx("F", "B", 5, 50)]
        self.assertEqual(material_funders(rows, "A", reg_block=100, threshold=0.2), [])

    def test_largest_first_and_capped_at_fifty(self):
        rows = [self.tx(f"F{i}", "A", 1 + i, 50) for i in range(60)]
        out = material_funders(rows, "A", reg_block=100, threshold=0.2)
        self.assertEqual(len(out), 50)
        self.assertEqual(out[0]["frm"], "F59")


class ClusterTest(unittest.TestCase):
    def test_shared_private_funder_merges_two_wallets(self):
        part = cluster(["A", "B", "C"], funding={"A": [f("P")], "B": [f("P")], "C": [f("Q")]},
                       level2={}, profiles={"P": {"total": 12}})
        self.assertEqual(part.root("A"), part.root("B"))
        self.assertNotEqual(part.root("A"), part.root("C"))
        self.assertEqual(part.n_clusters(), 2)

    def test_shared_exchange_funder_does_not_merge(self):
        part = cluster(["A", "B"], funding={"A": [f("X")], "B": [f("X")]}, level2={},
                       profiles={"X": {"total": 5000}})
        self.assertNotEqual(part.root("A"), part.root("B"))

    def test_exactly_1500_transfers_is_not_yet_an_exchange(self):
        part = cluster(["A", "B"], funding={"A": [f("X")], "B": [f("X")]}, level2={},
                       profiles={"X": {"total": 1500}})
        self.assertEqual(part.root("A"), part.root("B"))

    def test_unprofiled_linking_address_does_not_merge(self):
        part = cluster(["A", "B"], funding={"A": [f("P")], "B": [f("P")]}, level2={}, profiles={})
        self.assertNotEqual(part.root("A"), part.root("B"))

    def test_direct_funding_between_two_traced_wallets_merges_them(self):
        part = cluster(["A", "B"], funding={"B": [f("A")]}, level2={}, profiles={})
        self.assertEqual(part.root("A"), part.root("B"))

    def test_second_level_link_through_small_funders(self):
        level2 = {"F1": {"total": 3, "rows": [f("G")]}, "F2": {"total": 4, "rows": [f("G")]}}
        part = cluster(["A", "B"], funding={"A": [f("F1")], "B": [f("F2")]}, level2=level2,
                       profiles={"G": {"total": 40}})
        self.assertEqual(part.root("A"), part.root("B"))

    def test_second_level_is_not_followed_through_busy_funders(self):
        level2 = {"F1": {"total": 101, "rows": [f("G")]}, "F2": {"total": 4, "rows": [f("G")]}}
        part = cluster(["A", "B"], funding={"A": [f("F1")], "B": [f("F2")]}, level2=level2,
                       profiles={"G": {"total": 40}})
        self.assertNotEqual(part.root("A"), part.root("B"))

    def test_shared_ip_merges_only_in_best_lens(self):
        kw = dict(funding={}, level2={}, profiles={}, ips={"A": {"1.2.3.4"}, "B": {"1.2.3.4"}, "C": {"9.9.9.9"}})
        self.assertNotEqual(cluster(["A", "B", "C"], mode="lower", **kw).root("A"),
                            cluster(["A", "B", "C"], mode="lower", **kw).root("B"))
        best = cluster(["A", "B", "C"], mode="best", **kw)
        self.assertEqual(best.root("A"), best.root("B"))
        self.assertNotEqual(best.root("A"), best.root("C"))

    def test_batch_withdrawal_from_one_exchange_merges_only_in_best_lens(self):
        funding = {"A": [f("X", 1.00, 1000)], "B": [f("X", 1.05, 1030)], "C": [f("X", 1.00, 5000)],
                   "D": [f("X", 3.00, 1010)]}
        profiles = {"X": {"total": 90000}}
        lower = cluster("ABCD", funding=funding, level2={}, profiles=profiles, mode="lower")
        self.assertEqual(lower.n_clusters(), 4)
        best = cluster("ABCD", funding=funding, level2={}, profiles=profiles, mode="best")
        self.assertEqual(best.root("A"), best.root("B"))      # 30 blocks apart, 5% apart
        self.assertNotEqual(best.root("A"), best.root("C"))   # 4,000 blocks apart
        self.assertNotEqual(best.root("A"), best.root("D"))   # amounts differ by a factor of 3

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            cluster(["A"], funding={}, level2={}, profiles={}, mode="broad")


class SummaryTest(unittest.TestCase):
    def test_counts_shares_and_owner_exclusion(self):
        shares = {"A": 0.40, "B": 0.20, "C": 0.20, "D": 0.10, "E": 0.10}
        out = lineage_summary(
            shares, sample=["A", "B", "C", "D"],
            funding={"A": [f("P")], "B": [f("P")], "C": [f("X")], "D": [f("OWNER")]},
            level2={}, profiles={"P": {"total": 9}, "X": {"total": 9000}}, ips={},
            owner_addresses={"OWNER"}, owner_side=set(),
        )
        # D is owner-linked (10%). Remaining 90%: {A+B} 60, C 20, E 10 (E untraced, counted as its own wallet)
        self.assertAlmostEqual(out["owner_linked_share"], 0.10)
        self.assertEqual(out["clusters_lb"], 3)
        self.assertEqual(out["clusters_best"], 3)
        self.assertAlmostEqual(out["hhi_best"], (0.6 / 0.9) ** 2 + (0.2 / 0.9) ** 2 + (0.1 / 0.9) ** 2)
        self.assertAlmostEqual(out["untraced_share"], 0.10)
        # C is a traced singleton whose only funder is an exchange: it cannot be attributed
        self.assertAlmostEqual(out["unattrib_share"], 0.20)

    def test_owner_side_transfers_mark_a_wallet_as_owner_linked(self):
        out = lineage_summary({"A": 0.5, "B": 0.5}, sample=["A", "B"], funding={}, level2={}, profiles={},
                              ips={}, owner_addresses={"OWNER"}, owner_side={"B"})
        self.assertAlmostEqual(out["owner_linked_share"], 0.5)
        self.assertEqual(out["clusters_lb"], 1)

    def test_wallet_in_the_same_lineage_as_an_owner_funded_wallet_is_owner_linked(self):
        out = lineage_summary({"A": 0.5, "B": 0.3, "C": 0.2}, sample=["A", "B", "C"],
                              funding={"A": [f("OWNER"), f("P")], "B": [f("P")]}, level2={},
                              profiles={"P": {"total": 5}}, ips={}, owner_addresses={"OWNER"}, owner_side=set())
        self.assertAlmostEqual(out["owner_linked_share"], 0.8)
        self.assertEqual(out["clusters_lb"], 1)

    def test_everything_owner_linked_gives_missing_concentration(self):
        out = lineage_summary({"A": 1.0}, sample=["A"], funding={"A": [f("OWNER")]}, level2={}, profiles={},
                              ips={}, owner_addresses={"OWNER"}, owner_side=set())
        self.assertAlmostEqual(out["owner_linked_share"], 1.0)
        self.assertIsNone(out["hhi_best"])
        self.assertEqual(out["clusters_lb"], 0)

    def test_no_paid_wallets(self):
        out = lineage_summary({}, sample=[], funding={}, level2={}, profiles={}, ips={},
                              owner_addresses={"OWNER"}, owner_side=set())
        self.assertIsNone(out["hhi_best"])
        self.assertIsNone(out["owner_linked_share"])


if __name__ == "__main__":
    unittest.main()
