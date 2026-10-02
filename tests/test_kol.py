import unittest

from snprice.kol import screen

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


if __name__ == "__main__":
    unittest.main()
