import unittest

from snprice.teams import team_ids


def row(netuid, gh=None, site=None, contact=None, x=None):
    return {"netuid": netuid, "gh_owner": gh, "website_url": site, "contact_domain": contact, "x_handle": x}


class TeamIdsTest(unittest.TestCase):
    def test_subnet_on_its_own_is_its_own_team(self):
        out = team_ids([row(64, gh="chutesai", site="https://chutes.ai")])
        self.assertEqual(out[64], {"team_id": "T064", "team_n_subnets": 1})

    def test_same_github_owner_is_one_team_named_after_its_lowest_netuid(self):
        out = team_ids([row(1, gh="macrocosm-os"), row(9, gh="Macrocosm-OS"), row(13, gh="macrocosm-os"), row(64, gh="chutesai")])
        self.assertEqual({out[n]["team_id"] for n in (1, 9, 13)}, {"T001"})
        self.assertEqual(out[9]["team_n_subnets"], 3)
        self.assertEqual(out[64]["team_n_subnets"], 1)

    def test_same_site_domain_contact_domain_or_x_account_also_links(self):
        out = team_ids([row(48, site="https://www.qbittensorlabs.com/"), row(63, site="https://qbittensorlabs.com/enigma"),
                        row(24, contact="silxinc.com"), row(27, contact="silxinc.com"),
                        row(19, x="taostats"), row(28, x="TaoStats")])
        self.assertEqual(out[48]["team_id"], out[63]["team_id"])
        self.assertEqual(out[24]["team_id"], out[27]["team_id"])
        self.assertEqual(out[19]["team_id"], out[28]["team_id"])

    def test_links_chain(self):
        # 1 and 2 share the repository owner, 2 and 3 share the site
        out = team_ids([row(1, gh="a"), row(2, gh="a", site="https://b.ai"), row(3, site="https://b.ai/x")])
        self.assertEqual({out[n]["team_id"] for n in (1, 2, 3)}, {"T001"})
        self.assertEqual(out[3]["team_n_subnets"], 3)

    def test_placeholders_and_shared_hosts_link_nobody(self):
        out = team_ids([row(39, gh="deprecated"), row(42, gh="deprecated"),
                        row(5, site="https://a.github.io/x"), row(6, site="https://b.github.io/y"),
                        row(7, site="https://one.vercel.app"), row(8, site="https://two.vercel.app")])
        self.assertEqual(len({out[n]["team_id"] for n in (39, 42, 5, 6, 7, 8)}), 6)

    def test_site_stored_on_another_projects_storage_service_is_not_that_projects_team(self):
        out = team_ids([row(75, gh="thenervelab", site="https://hippius.com/"),
                        row(97, gh="unarbos", site="https://us-east-1.hippius.com/albedo/index.html")])
        self.assertNotEqual(out[75]["team_id"], out[97]["team_id"])

    def test_missing_values_link_nobody(self):
        out = team_ids([row(1), row(2), row(3, gh="", site="", contact="", x="")])
        self.assertEqual(len({out[n]["team_id"] for n in (1, 2, 3)}), 3)


if __name__ == "__main__":
    unittest.main()
