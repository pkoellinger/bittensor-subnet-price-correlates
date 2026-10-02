import unittest

from snprice.textmatch import (Matcher, speaker_affiliations, spoken_ids, subnet_entries, subnets_of_affiliation,
                               valid_for_project)

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

    def test_alias_is_distinctive_even_when_the_name_is_a_common_word(self):
        m = Matcher([{"netuid": 111, "name": "Claims", "handles": [], "aliases": ["DeSci Claims"], "rule": "strict"},
                     {"netuid": 9, "name": "iota", "handles": [], "aliases": ["IOTA subnet nine"], "rule": "context"}])
        hit = m.find("DeSci Claims launched today")
        self.assertEqual(hit[111]["strength"], "strong")
        self.assertEqual(m.find("the IOTA subnet nine launch")[9]["strength"], "strong")

    def test_common_word_name_followed_by_its_own_number_is_strong(self):
        hit = self.m.find("4 Subnets // Cacheon 14, Cathedral 39, Score 44, Claims 111")
        self.assertEqual({n for n, h in hit.items() if h["strength"] == "strong"}, {44, 111})
        self.assertEqual(set(hit[44]["rules"]), {"name", "id"})

    def test_common_word_name_followed_by_another_number_is_not_a_mention(self):
        self.assertEqual(self.m.find("Score 45 points and Claims 11 times"), {})
        self.assertEqual(self.m.find("Score 440"), {})

    def test_ordinary_adjective_before_the_word_subnet_is_not_a_mention(self):
        m = Matcher([{"netuid": 95, "name": "Actual", "handles": [], "aliases": [], "rule": "strict"}])
        self.assertEqual(m.find("from an actual subnet perspective on Bittensor"), {})
        self.assertEqual(m.find("for the actual subnet themselves"), {})
        self.assertEqual(m.find("the Actual subnet prices energy")[95]["strength"], "strong")
        self.assertEqual(m.find("the Actual Subnet prices energy")[95]["strength"], "strong")

    # --- numbers written as words (speech transcripts)
    def test_spoken_numbers_are_off_by_default(self):
        self.assertEqual(self.m.find("we built subnet sixty-four"), {})

    def test_spoken_number_after_subnet(self):
        for text in ("we built Subnet sixty-four on Bittensor", "subnet sixty four.", "netuid sixty-four, and"):
            hit = self.m.find(text, spoken_numbers=True)
            self.assertEqual(set(hit), {64}, text)
            self.assertEqual(hit[64]["rules"], ["id_spoken"])

    def test_spoken_number_confirms_a_common_word_name(self):
        hit = self.m.find("If you are fans of Subnet forty-four, Score has made progress", spoken_numbers=True)
        self.assertEqual(hit[44]["strength"], "strong")
        self.assertEqual(set(hit[44]["rules"]), {"id_spoken", "name"})

    def test_several_subnets_in_one_text(self):
        self.assertEqual(self.strong("SN64, SN51 and Chutes again"), {64, 51})

    def test_rules_that_fired_are_reported(self):
        hit = self.m.find("Chutes (SN64) by @chutes_ai")[64]
        self.assertEqual(set(hit["rules"]), {"id", "handle", "name"})

    def test_empty_text(self):
        self.assertEqual(self.m.find(""), {})
        self.assertEqual(self.m.find(None), {})


class SpokenIdsTest(unittest.TestCase):
    def ids(self, text):
        return spoken_ids(text)

    def test_cardinals(self):
        self.assertEqual(self.ids("we gave it to subnet fourteen, and we said"), [14])
        self.assertEqual(self.ids("Subnet forty-four"), [44])
        self.assertEqual(self.ids("subnet forty four"), [44])
        self.assertEqual(self.ids("I will use Subnet Seventeen as an example"), [17])
        self.assertEqual(self.ids("subnet ten is well-positioned"), [10])
        self.assertEqual(self.ids("buyback on the subnet four token"), [4])
        self.assertEqual(self.ids("Open Roboto, subnet eighty. And we see"), [80])

    def test_number_keyword(self):
        self.assertEqual(self.ids("Teutonic, subnet number three, and Open Roboto"), [3])

    def test_digit_by_digit(self):
        self.assertEqual(self.ids("This is subnet one one two. We're focused"), [112])
        self.assertEqual(self.ids("founder of Beam, Subnet one oh five on Bittensor"), [105])

    def test_hundreds(self):
        self.assertEqual(self.ids("subnet one hundred and eleven"), [111])
        self.assertEqual(self.ids("subnet one hundred eleven"), [111])
        self.assertEqual(self.ids("subnet one hundred twenty-eight"), [128])
        self.assertEqual(self.ids("subnet one eleven"), [111])
        self.assertEqual(self.ids("subnet one twenty"), [120])
        self.assertEqual(self.ids("subnet one twenty-four"), [124])

    def test_several(self):
        self.assertEqual(self.ids("subnet ninety, like I said, with GM, the subnet twenty-eight."), [90, 28])

    def test_a_quantity_is_not_a_subnet_number(self):
        self.assertEqual(self.ids("we've only had the subnet four months"), [])
        self.assertEqual(self.ids("we ran the subnet two years ago"), [])
        self.assertEqual(self.ids("a great subnet one of the best"), [])
        self.assertEqual(self.ids("the subnet three times"), [])

    def test_number_one_is_a_rank(self):
        self.assertEqual(self.ids("the subnet number one for so many months"), [])

    def test_words_that_do_not_form_a_number_are_rejected(self):
        self.assertEqual(self.ids("subnet twenty-nineteen"), [])
        self.assertEqual(self.ids("subnet forty fourteen"), [])
        self.assertEqual(self.ids("subnet hundred"), [])

    def test_trigger_must_be_the_singular_word(self):
        self.assertEqual(self.ids("subnets one and two"), [])
        self.assertEqual(self.ids("SN twenty"), [])
        self.assertEqual(self.ids("twenty subnets"), [])

    def test_digits_are_left_to_the_id_rule(self):
        self.assertEqual(self.ids("subnet 64"), [])

    def test_empty(self):
        self.assertEqual(self.ids(""), [])
        self.assertEqual(self.ids(None), [])


class EntriesTest(unittest.TestCase):
    def test_entries_combine_roster_links_and_alias_table(self):
        roster = [{"netuid": "111", "subnet_name": "Claims"}, {"netuid": "35", "subnet_name": None}]
        links = [{"netuid": "111", "x_handle": "DeSciClaims"}, {"netuid": "35", "x_handle": None}]
        alias = [{"netuid": "111", "rule": "strict", "aliases": "DeSci Claims|", "team_aliases": "Luminto"},
                 {"netuid": "35", "rule": "placeholder", "aliases": "", "team_aliases": ""}]
        out = subnet_entries(roster, links, alias)
        self.assertEqual(out[0], {"netuid": 111, "name": "Claims", "rule": "strict", "handles": ["DeSciClaims"],
                                  "aliases": ["DeSci Claims"], "team_aliases": ["Luminto"]})
        self.assertEqual(out[1]["rule"], "placeholder")
        self.assertEqual(out[1]["handles"], [])

    def test_subnet_missing_from_the_alias_table_is_an_error(self):
        with self.assertRaises(KeyError):
            subnet_entries([{"netuid": "1", "subnet_name": "Apex"}], [{"netuid": "1", "x_handle": None}], [])

    def test_team_lookup_is_case_insensitive_and_returns_all_subnets_of_the_team(self):
        entries = [
            {"netuid": 1, "name": "Apex", "rule": "strict", "handles": [], "aliases": [], "team_aliases": ["Macrocosmos"]},
            {"netuid": 9, "name": "iota", "rule": "context", "handles": [], "aliases": [], "team_aliases": ["Macrocosmos"]},
            {"netuid": 111, "name": "Claims", "rule": "strict", "handles": [], "aliases": ["DeSci Claims"], "team_aliases": []},
        ]
        self.assertEqual(subnets_of_affiliation("macrocosmos", entries), {1, 9})
        self.assertEqual(subnets_of_affiliation("Claims", entries), {111})         # a subnet's own name
        self.assertEqual(subnets_of_affiliation("DeSci Claims", entries), {111})   # or alias
        self.assertEqual(subnets_of_affiliation("Bitcast, SN93", entries + [
            {"netuid": 93, "name": "Bitcast", "rule": "plain", "handles": [], "aliases": [], "team_aliases": []}]), {93})
        self.assertEqual(subnets_of_affiliation("Tao.com", entries), set())
        self.assertEqual(subnets_of_affiliation("", entries), set())

    def test_team_of_a_subnet_with_placeholder_identity_is_found_by_its_team_name_only(self):
        entries = [{"netuid": 112, "name": "for sale", "rule": "placeholder", "handles": [], "aliases": [],
                    "team_aliases": ["Khala Research"]}]
        self.assertEqual(subnets_of_affiliation("Khala Research", entries), {112})
        self.assertEqual(subnets_of_affiliation("For Sale", entries), set())


class SpeakerAffiliationsTest(unittest.TestCase):
    def test_labels_in_brackets(self):
        self.assertEqual(speaker_affiliations("Will Squires and Steffen Cruz (Macrocosmos)"), ["Macrocosmos"])
        self.assertEqual(speaker_affiliations("Jose Caldera (Yanez), Seby Rubino (Bigtensor)"), ["Yanez", "Bigtensor"])

    def test_moderators_are_left_out(self):
        text = "Keith Singery (Tao.com), Brien Colwell (UR Foundation); moderated by Jack Ai Leung (Khala Research)"
        self.assertEqual(speaker_affiliations(text), ["Tao.com", "UR Foundation"])
        self.assertEqual(speaker_affiliations("A (X) Moderated by B (Y)"), ["X"])

    def test_no_speakers(self):
        self.assertEqual(speaker_affiliations(None), [])
        self.assertEqual(speaker_affiliations("Jane Doe"), [])


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
