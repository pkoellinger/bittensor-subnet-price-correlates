import unittest

from snprice.handles import candidate_handles, profile_matches


def profile(username, name="", description="", site=None):
    p = {"username": username, "name": name, "description": description}
    if site:
        p["entities"] = {"url": {"urls": [{"url": "https://t.co/abc", "expanded_url": site}]}}
    return p


class CandidateHandlesTest(unittest.TestCase):
    def test_variants_of_the_name_the_repository_owner_and_the_site(self):
        out = candidate_handles("Teutonic", "unarbos", "https://www.teutonic.ai/")
        for expected in ("teutonic", "teutonicai", "teutonic_ai", "teutonichq", "teutonic_io", "unarbos"):
            self.assertIn(expected, out)
        self.assertEqual(len(out), len(set(out)))

    def test_names_are_reduced_to_handle_characters(self):
        self.assertIn("streetvisionbyn", candidate_handles("StreetVision by NATIX", None, None))
        self.assertIn("itsai", candidate_handles("It's AI", None, None))

    def test_handles_longer_than_fifteen_characters_are_cut_or_left_out(self):
        for h in candidate_handles("A Very Long Subnet Name Indeed", "an-organisation-with-a-long-name", None):
            self.assertLessEqual(len(h), 15)
            self.assertRegex(h, r"^[A-Za-z0-9_]+$")

    def test_very_short_stems_are_not_guessed(self):
        self.assertEqual(candidate_handles("UR", None, "https://ur.xyz"), ["ur_ai", "ur_io"])

    def test_nothing_to_go_on(self):
        self.assertEqual(candidate_handles(None, None, None), [])


class ProfileMatchesTest(unittest.TestCase):
    def test_profile_that_links_the_subnets_site(self):
        p = profile("affine_io", "Affine", "Reasoning commodity", site="https://www.affine.io/docs")
        self.assertEqual(profile_matches(p, 120, "Affine", "www.affine.io"), "site")

    def test_profile_that_names_the_subnet_and_its_number(self):
        p = profile("hone_agi", "Hone", "Chasing AGI on Bittensor SN5")
        self.assertEqual(profile_matches(p, 5, "Hone", None), "name and number")
        p = profile("hone_agi", "Hone", "Bittensor subnet 5. ARC-AGI.")
        self.assertEqual(profile_matches(p, 5, "Hone", "https://honedashboard.com"), "name and number")

    def test_number_alone_or_name_alone_is_not_enough(self):
        self.assertIsNone(profile_matches(profile("templar", "Templar", "SN3 on Bittensor"), 3, "Teutonic", None))
        self.assertIsNone(profile_matches(profile("hone", "Hone Knives", "Sharpening since 1990"), 5, "Hone", None))

    def test_another_number_does_not_match(self):
        self.assertIsNone(profile_matches(profile("hone_agi", "Hone", "Bittensor SN50"), 5, "Hone", None))

    def test_site_on_another_domain_does_not_match(self):
        p = profile("affine", "Affine", "Design software", site="https://affine.pro")
        self.assertIsNone(profile_matches(p, 120, "Affine", "https://www.affine.io"))

    def test_profile_without_details(self):
        self.assertIsNone(profile_matches({"username": "x"}, 1, "Apex", "https://apex.macrocosmos.ai"))


if __name__ == "__main__":
    unittest.main()
