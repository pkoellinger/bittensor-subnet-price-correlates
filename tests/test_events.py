import unittest

from snprice.events import (
    basket_flows,
    contact_domain,
    contact_without_mailbox,
    last_real_identity_change,
    net_owner_trades,
    observed_window,
)

RAO = 10 ** 9


def ev(action, alpha, tao, extrinsic, is_transfer=None, block=100):
    return {"action": action, "alpha": str(int(alpha * RAO)), "amount": str(int(tao * RAO)),
            "extrinsic_id": extrinsic, "is_transfer": is_transfer, "block_number": block}


class OwnerTradesTest(unittest.TestCase):
    def test_buy_and_sell_are_summed_separately(self):
        out = net_owner_trades([ev("DELEGATE", 100, 2.0, "1-1"), ev("UNDELEGATE", 40, 0.9, "2-1")])
        self.assertAlmostEqual(out["buy_tao"], 2.0)
        self.assertAlmostEqual(out["sell_tao"], 0.9)
        self.assertAlmostEqual(out["net_buy_tao"], 1.1)
        self.assertAlmostEqual(out["sell_alpha"], 40)
        self.assertEqual((out["n_buys"], out["n_sells"]), (1, 1))

    def test_move_between_validators_is_not_a_trade(self):
        # same extrinsic, identical alpha on both legs: stake moved from one hotkey to another
        out = net_owner_trades([
            ev("UNDELEGATE", 458139.07516399, 39397.8, "8815326-0021"),
            ev("DELEGATE", 458139.07516399, 39397.8, "8815326-0021"),
        ])
        self.assertEqual(out["buy_tao"], 0)
        self.assertEqual(out["sell_tao"], 0)
        self.assertEqual((out["n_buys"], out["n_sells"]), (0, 0))

    def test_unequal_legs_in_one_extrinsic_are_trades(self):
        out = net_owner_trades([ev("UNDELEGATE", 100, 2.0, "5-1"), ev("DELEGATE", 60, 1.2, "5-1")])
        self.assertAlmostEqual(out["sell_tao"], 2.0)
        self.assertAlmostEqual(out["buy_tao"], 1.2)

    def test_equal_alpha_in_different_extrinsics_is_not_netted(self):
        out = net_owner_trades([ev("UNDELEGATE", 100, 2.0, "5-1"), ev("DELEGATE", 100, 2.1, "6-1")])
        self.assertAlmostEqual(out["sell_tao"], 2.0)
        self.assertAlmostEqual(out["buy_tao"], 2.1)

    def test_transfers_are_dropped(self):
        out = net_owner_trades([ev("UNDELEGATE", 100, 2.0, "7-1", is_transfer=True)])
        self.assertEqual(out["sell_tao"], 0)
        self.assertAlmostEqual(out["transfer_out_alpha"], 100)

    def test_only_one_pair_is_removed_when_three_legs_share_alpha(self):
        out = net_owner_trades([
            ev("UNDELEGATE", 50, 1.0, "9-1"), ev("DELEGATE", 50, 1.0, "9-1"), ev("DELEGATE", 50, 1.0, "9-1"),
        ])
        self.assertAlmostEqual(out["buy_tao"], 1.0)
        self.assertEqual(out["sell_tao"], 0)

    def test_no_events(self):
        out = net_owner_trades([])
        self.assertEqual(out["net_buy_tao"], 0)


def swap(hotkey, origin, dest, tao):
    return {"args": {"hotkey": hotkey, "originNetuid": origin, "destinationNetuid": dest,
                     "taoMid": str(int(tao * RAO)), "alphaSold": "1", "alphaBought": "1"}}


class BasketFlowsTest(unittest.TestCase):
    def test_destination_gains_and_origin_loses_the_tao_value(self):
        out = basket_flows([swap("v1", 81, 14, 0.15)])
        self.assertAlmostEqual(out[14]["net_tao"], 0.15)
        self.assertAlmostEqual(out[81]["net_tao"], -0.15)

    def test_flows_sum_to_zero_over_all_netuids_including_root(self):
        events = [swap("v1", 81, 14, 0.15), swap("v2", 0, 64, 3.0), swap("v1", 64, 0, 1.0), swap("v3", 9, 64, 0.4)]
        out = basket_flows(events)
        self.assertAlmostEqual(sum(v["net_tao"] for v in out.values()), 0.0)

    def test_net_buyers_counts_baskets_with_positive_net(self):
        events = [swap("v1", 9, 64, 1.0), swap("v2", 9, 64, 0.5), swap("v3", 64, 9, 2.0), swap("v1", 64, 9, 0.2)]
        out = basket_flows(events)
        self.assertEqual(out[64]["net_buyers"], 2)   # v1 (+0.8) and v2 (+0.5); v3 is a net seller
        self.assertEqual(out[9]["net_buyers"], 1)    # v3

    def test_no_events(self):
        self.assertEqual(basket_flows([]), {})


def ident(block, name, repo="", url=""):
    return {"block_number": block, "subnet_name": name, "github_repo": repo, "subnet_url": url}


class IdentityChangeTest(unittest.TestCase):
    def test_sn111_history_gives_the_repo_owner_change(self):
        rows = [
            ident(5760114, "oneoneone", "https://github.com/oneoneone-io/subnet-111"),
            ident(8413360, "Claims", "https://github.com/oneoneone-io/subnet-111"),
            ident(8476377, "Claims", "https://github.com/DeSciClaims/Claims"),
        ]
        out = last_real_identity_change(rows, registered_block=5615562)
        self.assertEqual(out["block"], 8476377)
        self.assertEqual(out["what"], "github_owner")

    def test_first_identity_after_registration_is_not_a_change(self):
        self.assertIsNone(last_real_identity_change([ident(200, "Alpha", "https://github.com/a/b")], registered_block=100))

    def test_cosmetic_edits_do_not_count(self):
        rows = [
            ident(200, "Chutes", "https://github.com/chutesai/chutes", "https://chutes.ai"),
            ident(300, "chutes!", "https://github.com/chutesai/chutes-miner", "https://www.chutes.ai/"),
        ]
        self.assertIsNone(last_real_identity_change(rows, registered_block=100))

    def test_filling_a_blank_field_does_not_count(self):
        rows = [ident(200, "Alpha", "", ""), ident(300, "Alpha", "https://github.com/a/b", "https://alpha.ai")]
        self.assertIsNone(last_real_identity_change(rows, registered_block=100))

    def test_name_change_counts(self):
        rows = [ident(200, "Alpha", "https://github.com/a/b"), ident(300, "Beta", "https://github.com/a/b")]
        out = last_real_identity_change(rows, registered_block=100)
        self.assertEqual((out["block"], out["what"]), (300, "name"))

    def test_site_host_change_counts(self):
        rows = [ident(200, "Alpha", "", "https://alpha.ai"), ident(300, "Alpha", "", "https://other.io/home")]
        self.assertEqual(last_real_identity_change(rows, registered_block=100)["what"], "site_host")

    def test_events_before_registration_belong_to_the_previous_occupant(self):
        rows = [ident(50, "Old project", "https://github.com/old/x"), ident(200, "New project", "https://github.com/new/y")]
        self.assertIsNone(last_real_identity_change(rows, registered_block=100))

    def test_org_style_github_urls_are_understood(self):
        rows = [ident(200, "Beam", "https://github.com/orgs/Beam-Network/repositories"),
                ident(300, "Beam", "https://github.com/beam-network/subnet")]
        self.assertIsNone(last_real_identity_change(rows, registered_block=100))

    def test_rows_may_arrive_in_any_order(self):
        rows = [ident(300, "Beta"), ident(200, "Alpha")]
        self.assertEqual(last_real_identity_change(rows, registered_block=100)["block"], 300)


class ContactTest(unittest.TestCase):
    def test_email_is_reduced_to_its_domain(self):
        self.assertEqual(contact_without_mailbox("hello@macrocosmos.ai"), "@macrocosmos.ai")
        self.assertEqual(contact_without_mailbox("write to Jane.Doe+sn@Example.co.uk please"),
                         "write to @example.co.uk please")

    def test_urls_and_handles_are_kept(self):
        self.assertEqual(contact_without_mailbox("https://x.com/SomaSubnet"), "https://x.com/SomaSubnet")
        self.assertEqual(contact_without_mailbox("RomAI"), "RomAI")

    def test_empty(self):
        self.assertEqual(contact_without_mailbox(None), "")
        self.assertEqual(contact_without_mailbox("  "), "")

    def test_contact_domain(self):
        self.assertEqual(contact_domain("hello@macrocosmos.ai"), "macrocosmos.ai")
        self.assertEqual(contact_domain("someone@gmail.com"), "")      # generic mailbox providers link nobody
        self.assertEqual(contact_domain("https://x.com/SomaSubnet"), "")
        self.assertEqual(contact_domain(None), "")


class ObservedWindowTest(unittest.TestCase):
    BLOCKS = [100, 200, 300, 400]

    def test_subnet_older_than_the_window_sees_all_blocks(self):
        self.assertEqual(observed_window(self.BLOCKS, registered_block=5), [100, 200, 300, 400])

    def test_subnet_registered_inside_the_window_sees_only_later_blocks(self):
        self.assertEqual(observed_window(self.BLOCKS, registered_block=250), [300, 400])

    def test_subnet_registered_after_the_window_sees_nothing(self):
        self.assertEqual(observed_window(self.BLOCKS, registered_block=999), [])

    def test_registration_block_itself_is_observed(self):
        self.assertEqual(observed_window(self.BLOCKS, registered_block=300), [300, 400])


if __name__ == "__main__":
    unittest.main()
