import unittest

from snprice.kol import agreed_polarity, mention_counts, screen

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
