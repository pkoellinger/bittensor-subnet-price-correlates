import unittest

from snprice.textmatch import Matcher, valid_for_project

SUBNETS = [
    {"netuid": 64, "name": "Chutes", "handles": ["chutes_ai"], "aliases": [], "rule": "plain"},
    {"netuid": 51, "name": "lium.io", "handles": ["lium_io"], "aliases": ["Lium"], "rule": "plain"},
    {"netuid": 9, "name": "iota", "handles": ["macrocosmosai"], "aliases": [], "rule": "context"},
    {"netuid": 13, "name": "Data Universe", "handles": ["macrocosmosai"], "aliases": [], "rule": "plain"},
    {"netuid": 111, "name": "Claims", "handles": ["DeSciClaims"], "aliases": [], "rule": "strict"},
    {"netuid": 44, "name": "Score", "handles": ["webuildscore"], "aliases": [], "rule": "strict"},
    {"netuid": 17, "name": "404—GEN", "handles": ["404gen_"], "aliases": ["404-GEN", "404GEN"], "rule": "plain"},
    {"netuid": 35, "name": "Unknown", "handles": [], "aliases": [], "rule": "placeholder"},
    {"netuid": 112, "name": "for sale", "handles": [], "aliases": [], "rule": "placeholder"},
]


class MatcherTest(unittest.TestCase):
    def setUp(self):
        self.m = Matcher(SUBNETS)

    def strong(self, text, **kw):
        return {n for n, hit in self.m.find(text, **kw).items() if hit["strength"] == "strong"}

    def weak(self, text, **kw):
        return {n for n, hit in self.m.find(text, **kw).items() if hit["strength"] == "weak"}

    # --- ids
    def test_sn_number(self):
        self.assertEqual(self.strong("SN64 is cooking"), {64})

    def test_id_spellings(self):
        for text in ("sn 64", "SN-64", "Subnet 64", "subnet #64", "netuid 64", "Subnet-64:", "(SN64)"):
            self.assertEqual(self.strong(text), {64}, text)

    def test_longer_number_is_not_a_prefix_match(self):
        self.assertEqual(self.strong("SN640 does not exist"), set())

    def test_number_not_in_roster_is_ignored(self):
        self.assertEqual(self.strong("SN77 news"), set())

    def test_sn_inside_another_word_is_not_an_id(self):
        self.assertEqual(self.strong("this isn 64 times better"), set())

    def test_placeholder_subnet_can_be_matched_by_id_only(self):
        self.assertEqual(self.strong("SN35 was just registered"), {35})
        self.assertEqual(self.m.find("an Unknown subnet is for sale on Bittensor"), {})

    # --- handles
    def test_handle(self):
        self.assertEqual(self.strong("congrats @Chutes_AI on the launch"), {64})

    def test_handle_shared_by_several_subnets_identifies_none(self):
        self.assertEqual(self.m.find("great work @macrocosmosai"), {})

    def test_handle_must_be_whole(self):
        self.assertEqual(self.m.find("@chutes_ai_fan posted"), {})

    # --- names
    def test_distinctive_name(self):
        self.assertEqual(self.strong("Chutes revenue is up"), {64})
        self.assertEqual(self.strong("chutes revenue is up"), {64})

    def test_name_must_be_a_whole_word(self):
        self.assertEqual(self.m.find("parachutes are fun"), {})

    def test_alias_and_name_with_punctuation(self):
        self.assertEqual(self.strong("renting GPUs on Lium today"), {51})
        self.assertEqual(self.strong("renting GPUs on lium.io today"), {51})
        self.assertEqual(self.strong("404-GEN ships 3D models"), {17})

    def test_context_name_needs_a_bittensor_term(self):
        self.assertEqual(self.m.find("not one iota of doubt"), {})
        self.assertEqual(self.strong("iota is the best subnet for training"), {9})
        self.assertEqual(self.strong("not one iota of doubt", assume_context=True), {9})

    def test_common_word_name_is_never_strong_by_name_alone(self):
        self.assertEqual(self.m.find("he claims the score is high"), {})
        self.assertEqual(self.strong("Bittensor: Claims and Score are shipping"), set())

    def test_common_word_name_in_exact_case_with_context_is_a_weak_candidate(self):
        self.assertEqual(self.weak("Bittensor: Claims and Score are shipping"), {111, 44})

    def test_common_word_name_without_context_is_nothing(self):
        self.assertEqual(self.m.find("Claims are processed within 5 days"), {})

    def test_common_word_name_next_to_a_subnet_marker_is_strong(self):
        self.assertEqual(self.strong("the Claims subnet extracts evidence"), {111})
        self.assertEqual(self.strong("subnet Score does computer vision"), {44})

    def test_common_word_name_with_its_id_or_handle_is_strong(self):
        self.assertEqual(self.strong("Claims (SN111) is live"), {111})
        self.assertEqual(self.strong("Score by @webuildscore"), {44})

    def test_several_subnets_in_one_text(self):
        self.assertEqual(self.strong("SN64, SN51 and Chutes again"), {64, 51})

    def test_rules_that_fired_are_reported(self):
        hit = self.m.find("Chutes (SN64) by @chutes_ai")[64]
        self.assertEqual(set(hit["rules"]), {"id", "handle", "name"})

    def test_empty_text(self):
        self.assertEqual(self.m.find(""), {})
        self.assertEqual(self.m.find(None), {})


class ProjectDateRuleTest(unittest.TestCase):
    def test_id_only_mention_before_project_start_belongs_to_the_previous_occupant(self):
        self.assertFalse(valid_for_project({"rules": ["id"]}, when="2026-07-01", project_start="2026-08-03"))

    def test_id_only_mention_after_project_start_counts(self):
        self.assertTrue(valid_for_project({"rules": ["id"]}, when="2026-08-10", project_start="2026-08-03"))

    def test_name_or_handle_mention_counts_whatever_the_date(self):
        self.assertTrue(valid_for_project({"rules": ["id", "name"]}, when="2026-07-01", project_start="2026-08-03"))
        self.assertTrue(valid_for_project({"rules": ["handle"]}, when="2026-07-01", project_start="2026-08-03"))

    def test_unknown_project_start_does_not_filter(self):
        self.assertTrue(valid_for_project({"rules": ["id"]}, when="2026-07-01", project_start=None))


if __name__ == "__main__":
    unittest.main()
