import unittest

from snprice.events import (
    basket_flows,
    contact_domain,
    contact_without_mailbox,
    last_real_identity_change,
    net_owner_trades,
    observed_window,
    owner_tenures,
    project_owner_keys,
    project_start,
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


def change(block, old, new):
    return {"block": block, "previous_owner": old, "owner": new}


class OwnerTenuresTest(unittest.TestCase):
    """Who owned the subnet in which blocks of a window (lo, hi]: trades count for the owner of the day."""

    def test_owner_that_never_changed_holds_the_whole_window(self):
        self.assertEqual(owner_tenures([], "NOW", 1000, 2000), [("NOW", 1000, 2000)])

    def test_new_owner_holds_the_subnet_from_the_block_of_the_change(self):
        out = owner_tenures([change(1500, "OLD", "NOW")], "NOW", 1000, 2000)
        self.assertEqual(out, [("OLD", 1000, 1499), ("NOW", 1499, 2000)])

    def test_two_changes_in_the_window(self):
        out = owner_tenures([change(1800, "MID", "NOW"), change(1200, "OLD", "MID")], "NOW", 1000, 2000)
        self.assertEqual(out, [("OLD", 1000, 1199), ("MID", 1199, 1799), ("NOW", 1799, 2000)])

    def test_changes_outside_the_window_are_ignored(self):
        out = owner_tenures([change(900, "OLD", "NOW"), change(2500, "NOW", "LATER")], "NOW", 1000, 2000)
        self.assertEqual(out, [("NOW", 1000, 2000)])

    def test_change_in_the_first_block_of_the_window_leaves_the_old_owner_nothing(self):
        self.assertEqual(owner_tenures([change(1001, "OLD", "NOW")], "NOW", 1000, 2000), [("NOW", 1000, 2000)])

    def test_history_that_does_not_end_at_the_known_owner_is_an_error(self):
        with self.assertRaises(ValueError):
            owner_tenures([change(1500, "OLD", "SOMEONE")], "NOW", 1000, 2000)


class ProjectOwnerKeysTest(unittest.TestCase):
    """Keys that owned the subnet while the current project ran: a team that moved to a new
    wallet is still the same team."""

    def test_owner_that_never_changed(self):
        self.assertEqual(project_owner_keys([], "NOW", project_start=1000), {"NOW"})

    def test_key_replaced_after_the_project_started_belongs_to_the_project(self):
        self.assertEqual(project_owner_keys([change(1500, "OLD", "NOW")], "NOW", project_start=1000), {"NOW", "OLD"})

    def test_key_replaced_before_the_project_started_is_somebody_else(self):
        self.assertEqual(project_owner_keys([change(900, "SELLER", "NOW")], "NOW", project_start=1000), {"NOW"})

    def test_several_changes(self):
        changes = [change(900, "SELLER", "FIRST"), change(1200, "FIRST", "SECOND"), change(1800, "SECOND", "NOW")]
        self.assertEqual(project_owner_keys(changes, "NOW", project_start=1000), {"NOW", "SECOND", "FIRST"})


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

    def test_new_name_that_extends_the_old_one_is_the_same_name(self):
        for old_name, new_name in (("gm", "SayGM"), ("AlphaRidge", "AlphaRidge.ai"), ("Bitsec.ai", "Bitsec"),
                                   ("Score", "Score Vision")):
            rows = [ident(200, old_name), ident(300, new_name)]
            self.assertIsNone(last_real_identity_change(rows, registered_block=100), (old_name, new_name))

    def test_short_name_inside_an_unrelated_longer_name_is_a_change(self):
        rows = [ident(200, "UR"), ident(300, "Aurelius")]
        self.assertEqual(last_real_identity_change(rows, registered_block=100)["what"], "name")

    def test_moving_the_site_to_a_subdomain_is_not_a_change(self):
        rows = [ident(200, "Cortex", "", "https://cortex.foundation"),
                ident(300, "Cortex", "", "https://network.cortex.foundation/app")]
        self.assertIsNone(last_real_identity_change(rows, registered_block=100))


class ProjectStartTest(unittest.TestCase):
    def test_sn111_project_starts_with_its_name_not_with_the_later_repo_move(self):
        rows = [
            ident(5760114, "oneoneone", "https://github.com/oneoneone-io/subnet-111"),
            ident(8413360, "Claims", "https://github.com/oneoneone-io/subnet-111"),
            ident(8476377, "Claims", "https://github.com/DeSciClaims/Claims"),
        ]
        self.assertEqual(project_start(rows, registered_block=5615562), 8413360)

    def test_repository_or_site_moves_alone_do_not_start_a_project(self):
        rows = [ident(200, "Chutes", "https://github.com/rayonlabs/chutes", "https://chutes.ai"),
                ident(300, "Chutes", "https://github.com/chutesai/chutes", "https://chutes.io")]
        self.assertIsNone(project_start(rows, registered_block=100))

    def test_latest_of_several_renames(self):
        rows = [ident(200, "Templar"), ident(300, "deprecated"), ident(400, "Teutonic"), ident(500, "Teutonic")]
        self.assertEqual(project_start(rows, registered_block=100), 400)

    def test_extended_name_does_not_start_a_project(self):
        self.assertIsNone(project_start([ident(200, "gm"), ident(300, "SayGM")], registered_block=100))

    def test_blank_name_between_two_names(self):
        # the name is cleared and later set to something new: the project starts with the new name
        rows = [ident(200, "Alpha"), ident(300, ""), ident(400, "Beta")]
        self.assertEqual(project_start(rows, registered_block=100), 400)
        rows = [ident(200, "Alpha"), ident(300, ""), ident(400, "Alpha")]
        self.assertIsNone(project_start(rows, registered_block=100))

    def test_events_of_a_previous_occupant_are_ignored(self):
        rows = [ident(50, "Old"), ident(200, "New")]
        self.assertIsNone(project_start(rows, registered_block=100))

    def test_rename_by_the_same_team_is_a_rebrand_not_a_new_project(self):
        rows = [ident(200, "Quantum Innovate", "https://github.com/qbittensor-labs/quantum"),
                ident(300, "Enigma", "https://github.com/qbittensor-labs/enigma")]
        self.assertIsNone(project_start(rows, registered_block=100))

    def test_project_starts_at_the_latest_rename_that_came_with_another_team(self):
        # x renames A to B (rebrand), then team y takes over and renames to C
        rows = [ident(200, "A", "https://github.com/x/a"), ident(300, "B", "https://github.com/x/b"),
                ident(400, "C", "https://github.com/y/c")]
        self.assertEqual(project_start(rows, registered_block=100), 400)
        # team y takes over with the rename to B, and later rebrands to C
        rows = [ident(200, "A", "https://github.com/x/a"), ident(300, "B", "https://github.com/y/b"),
                ident(400, "C", "https://github.com/y/c")]
        self.assertEqual(project_start(rows, registered_block=100), 300)

    def test_rename_without_a_known_repository_owner_counts_as_a_new_project(self):
        rows = [ident(200, "Alpha", ""), ident(300, "Beta", "https://github.com/y/b")]
        self.assertEqual(project_start(rows, registered_block=100), 300)
        rows = [ident(200, "Alpha", "https://github.com/x/a"), ident(300, "Beta", "")]
        self.assertEqual(project_start(rows, registered_block=100), 300)

    def test_no_events(self):
        self.assertIsNone(project_start([], registered_block=100))


class ContactTest(unittest.TestCase):
    def test_email_is_reduced_to_its_domain(self):
        self.assertEqual(contact_without_mailbox("hello@acme.ai"), "@acme.ai")
        self.assertEqual(contact_without_mailbox("write to Jane.Doe+sn@Example.co.uk please"),
                         "write to @example.co.uk please")

    def test_urls_and_handles_are_kept(self):
        self.assertEqual(contact_without_mailbox("https://x.com/SomaSubnet"), "https://x.com/SomaSubnet")
        self.assertEqual(contact_without_mailbox("RomAI"), "RomAI")

    def test_empty(self):
        self.assertEqual(contact_without_mailbox(None), "")
        self.assertEqual(contact_without_mailbox("  "), "")

    def test_contact_domain(self):
        self.assertEqual(contact_domain("hello@acme.ai"), "acme.ai")
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
