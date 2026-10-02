import unittest

from snprice.kol import agreed_polarity, mention_counts, mention_decision, post_mentions, post_text, screen
from snprice.textmatch import Matcher

PROFILE = {"username": "TaoOutsider", "public_metrics": {"followers_count": 12000}}


class ScreenTest(unittest.TestCase):
    def test_account_that_meets_every_rule(self):
        out = screen("TaoOutsider", PROFILE, original=300, bittensor=240, subnet_handles={"chutes_ai"})
        self.assertEqual(out, {"exists": 1, "independent": 1, "focus": 1, "activity": 1, "reach": 1,
                               "bittensor_share": 0.8, "passes": 1})

    def test_unknown_handle(self):
        out = screen("nobody", None, original=None, bittensor=None, subnet_handles=set())
        self.assertEqual(out["exists"], 0)
        self.assertEqual(out["passes"], 0)
        self.assertIsNone(out["bittensor_share"])

    def test_subnet_account_is_not_independent(self):
        out = screen("Chutes_AI", {"public_metrics": {"followers_count": 50000}}, 300, 290, {"chutes_ai"})
        self.assertEqual(out["independent"], 0)
        self.assertEqual(out["passes"], 0)

    def test_focus_needs_half_of_the_posts(self):
        self.assertEqual(screen("a", PROFILE, 100, 50, set())["focus"], 1)
        self.assertEqual(screen("a", PROFILE, 100, 49, set())["focus"], 0)

    def test_account_without_posts_has_no_share_and_fails(self):
        out = screen("a", PROFILE, 0, 0, set())
        self.assertIsNone(out["bittensor_share"])
        self.assertEqual((out["focus"], out["activity"], out["passes"]), (0, 0, 0))

    def test_activity_and_reach_thresholds(self):
        self.assertEqual(screen("a", PROFILE, 30, 30, set())["activity"], 1)
        self.assertEqual(screen("a", PROFILE, 29, 29, set())["activity"], 0)
        small = {"public_metrics": {"followers_count": 1999}}
        self.assertEqual(screen("a", small, 300, 300, set())["reach"], 0)
        self.assertEqual(screen("a", {"public_metrics": {"followers_count": 2000}}, 300, 300, set())["reach"], 1)


class AgreedPolarityTest(unittest.TestCase):
    def test_both_coders_must_agree_on_a_direction(self):
        self.assertEqual(agreed_polarity("positive", "positive"), "positive")
        self.assertEqual(agreed_polarity("negative", "negative"), "negative")

    def test_anything_else_is_neutral(self):
        self.assertEqual(agreed_polarity("positive", "neutral"), "neutral")
        self.assertEqual(agreed_polarity("positive", "negative"), "neutral")
        self.assertEqual(agreed_polarity("neutral", "neutral"), "neutral")

    def test_unknown_label_is_an_error(self):
        with self.assertRaises(ValueError):
            agreed_polarity("great", "positive")


class PostTextTest(unittest.TestCase):
    def test_short_post(self):
        self.assertEqual(post_text({"id": "1", "text": "SN64 ships"}), "SN64 ships")

    def test_long_post_carries_its_full_text_in_the_note(self):
        post = {"id": "1", "text": "SN64 ships a new… https://t.co/x", "note_tweet": {"text": "SN64 ships a new router today"}}
        self.assertEqual(post_text(post), "SN64 ships a new router today")

    def test_post_without_text(self):
        self.assertEqual(post_text({"id": "1"}), "")


class PostMentionsTest(unittest.TestCase):
    MATCHER = Matcher([
        {"netuid": 64, "name": "Chutes", "rule": "plain", "handles": ["chutes_ai"], "aliases": []},
        {"netuid": 111, "name": "Claims", "rule": "strict", "handles": [], "aliases": ["DeSci Claims"]},
        {"netuid": 82, "name": "", "rule": "placeholder", "handles": [], "aliases": []},
    ])
    START = {64: None, 111: "2026-06-15 10:00:00", 82: "2026-09-26 23:40:00"}

    def mentions(self, text, created="2026-09-10T12:00:00.000Z", **more):
        post = {"id": "77", "text": text, "created_at": created, **more}
        return post_mentions(post, "TaoOutsider", self.MATCHER, self.START)

    def test_post_that_names_a_subnet(self):
        self.assertEqual(self.mentions("Chutes keeps shipping"), [
            {"post_id": "77", "username": "TaoOutsider", "created": "2026-09-10T12:00:00Z", "netuid": 64,
             "strength": "strong", "rules": "name"}])

    def test_post_that_names_two_subnets_gives_two_rows(self):
        out = self.mentions("@chutes_ai and SN111 both shipped")
        self.assertEqual([(m["netuid"], m["rules"]) for m in out], [(64, "handle"), (111, "id")])

    def test_post_without_a_subnet(self):
        self.assertEqual(self.mentions("gm"), [])

    def test_number_alone_before_the_project_started_means_the_previous_occupant(self):
        self.assertEqual(self.mentions("SN82 looks dead", created="2026-09-01T08:00:00.000Z"), [])
        self.assertEqual([m["netuid"] for m in self.mentions("SN82 is back", created="2026-09-28T08:00:00.000Z")], [82])

    def test_ordinary_word_is_a_weak_candidate_and_only_in_a_post_about_bittensor(self):
        out = self.mentions("Claims is flying, best subnet this month")
        self.assertEqual([(m["netuid"], m["strength"]) for m in out], [(111, "weak")])
        self.assertEqual(self.mentions("Claims of a rally were wrong"), [])

    def test_long_post_is_matched_on_its_full_text(self):
        out = self.mentions("A thread on… https://t.co/x", note_tweet={"text": "A thread on DeSci Claims and why it matters"})
        self.assertEqual([m["netuid"] for m in out], [111])


class MentionDecisionTest(unittest.TestCase):
    """Does a matched post count for the subnet, and with which polarity?"""

    def test_strong_match_counts_with_the_direction_both_coders_chose(self):
        self.assertEqual(mention_decision("strong", "positive", "positive"), (True, "positive"))
        self.assertEqual(mention_decision("strong", "negative", "negative"), (True, "negative"))

    def test_direction_chosen_by_one_coder_only_is_neutral(self):
        self.assertEqual(mention_decision("strong", "positive", "neutral"), (True, "neutral"))
        self.assertEqual(mention_decision("strong", "positive", "negative"), (True, "neutral"))

    def test_strong_match_is_dropped_only_if_both_coders_say_it_is_not_about_the_subnet(self):
        self.assertEqual(mention_decision("strong", "not_about", "not_about"), (False, None))
        self.assertEqual(mention_decision("strong", "not_about", "positive"), (True, "neutral"))

    def test_weak_match_counts_only_if_no_coder_doubts_it(self):
        self.assertEqual(mention_decision("weak", "neutral", "positive"), (True, "neutral"))
        self.assertEqual(mention_decision("weak", "positive", "positive"), (True, "positive"))
        self.assertEqual(mention_decision("weak", "not_about", "positive"), (False, None))
        self.assertEqual(mention_decision("weak", "not_about", "not_about"), (False, None))

    def test_unknown_label_or_strength_is_an_error(self):
        with self.assertRaises(ValueError):
            mention_decision("strong", "great", "positive")
        with self.assertRaises(ValueError):
            mention_decision("certain", "positive", "positive")


DAY = 86400
T = 1000 * DAY


def mention(post, user, days_before_t, netuid, polarity="neutral"):
    return {"post_id": post, "username": user, "created": T - days_before_t * DAY, "netuid": netuid, "polarity": polarity}


class MentionCountsTest(unittest.TestCase):
    def counts(self, mentions):
        return mention_counts(mentions, t_end=T, window_days=90, month_days=30)

    def test_posts_accounts_and_polarity_in_90_days(self):
        out = self.counts([mention("1", "a", 5, 64, "positive"), mention("2", "a", 40, 64, "negative"),
                           mention("3", "b", 80, 64), mention("4", "b", 95, 64, "positive")])[64]
        self.assertEqual(out["kol_posts_90d"], 3)
        self.assertEqual(out["kol_accounts_90d"], 2)
        self.assertEqual(out["kol_pos_posts_90d"], 1)
        self.assertEqual(out["kol_neg_posts_90d"], 1)

    def test_last_month_and_the_month_before(self):
        out = self.counts([mention("1", "a", 5, 64, "positive"), mention("2", "a", 29, 64), mention("3", "a", 31, 64, "positive"),
                           mention("4", "a", 59, 64, "negative"), mention("5", "a", 61, 64)])[64]
        self.assertEqual((out["kol_posts_30d"], out["kol_posts_lag30"]), (2, 2))
        self.assertEqual((out["kol_pos_posts_30d"], out["kol_pos_posts_lag30"]), (1, 1))
        self.assertEqual((out["kol_neg_posts_30d"], out["kol_neg_posts_lag30"]), (0, 1))

    def test_post_naming_two_subnets_counts_for_each(self):
        out = self.counts([mention("1", "a", 5, 64), mention("1", "a", 5, 4)])
        self.assertEqual(out[64]["kol_posts_90d"], 1)
        self.assertEqual(out[4]["kol_posts_90d"], 1)

    def test_the_same_post_listed_twice_for_a_subnet_counts_once(self):
        out = self.counts([mention("1", "a", 5, 64), mention("1", "a", 5, 64)])
        self.assertEqual(out[64]["kol_posts_90d"], 1)

    def test_posts_after_t_are_ignored(self):
        self.assertEqual(self.counts([mention("1", "a", -1, 64)]), {})


if __name__ == "__main__":
    unittest.main()
