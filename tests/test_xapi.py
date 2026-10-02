import json
import os
import tempfile
import unittest

from snprice.fetch import BudgetExceeded, Ledger
from snprice.xapi import XClient, XError, load_approved

TOKEN = "AAAA-bearer-secret"


class Transport:
    def __init__(self, answers):
        self.answers = list(answers)
        self.urls = []

    def __call__(self, url, headers):
        self.urls.append(url)
        return self.answers.pop(0)


def users(names):
    return (200, json.dumps({"data": [{"id": str(i + 1), "username": n, "public_metrics": {"followers_count": 10}}
                                      for i, n in enumerate(names)]}))


def posts(ids, next_token=None):
    meta = {"result_count": len(ids)}
    if next_token:
        meta["next_token"] = next_token
    return (200, json.dumps({"data": [{"id": str(i), "text": "t", "created_at": "2026-09-01T00:00:00Z"} for i in ids],
                             "meta": meta}))


class XClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def client(self, answers, ceiling=50.0, approved=()):
        self.transport = Transport(answers)
        self.ledger = Ledger(os.path.join(self.tmp.name, "ledger.json"), {"x_usd": ceiling})
        return XClient(TOKEN, ledger=self.ledger, cache_dir=os.path.join(self.tmp.name, "x"),
                       transport=self.transport, approved=set(approved), sleep=lambda s: None)

    def test_user_lookup_costs_one_cent_per_user(self):
        c = self.client([users(["a", "b", "c"])])
        out = c.users_by(["a", "b", "c"])
        self.assertEqual([u["username"] for u in out], ["a", "b", "c"])
        self.assertAlmostEqual(self.ledger.used("x_usd"), 0.03)

    def test_user_lookup_is_split_into_batches_of_100(self):
        names = [f"u{i}" for i in range(150)]
        c = self.client([users(names[:100]), users(names[100:])])
        self.assertEqual(len(c.users_by(names)), 150)
        self.assertEqual(len(self.transport.urls), 2)

    def test_request_over_the_cap_is_refused_before_sending(self):
        c = self.client([users(["a", "b", "c"])], ceiling=0.02)
        with self.assertRaises(BudgetExceeded):
            c.users_by(["a", "b", "c"])
        self.assertEqual(self.transport.urls, [])
        self.assertEqual(self.ledger.used("x_usd"), 0)

    def test_posts_of_an_unapproved_account_are_never_read(self):
        c = self.client([posts([1, 2])], approved=["someone_else"])
        with self.assertRaises(PermissionError):
            c.user_posts("42", "kol_one", "2026-07-03T00:00:00Z", "2026-10-01T00:00:00Z")
        self.assertEqual(self.transport.urls, [])
        self.assertEqual(self.ledger.used("x_usd"), 0)

    def test_post_reads_are_settled_to_the_number_returned(self):
        c = self.client([posts(range(100), next_token="n1"), posts(range(100, 130))], approved=["KOL_One"])
        out = c.user_posts("42", "kol_one", "2026-07-03T00:00:00Z", "2026-10-01T00:00:00Z")
        self.assertEqual(len(out), 130)
        self.assertAlmostEqual(self.ledger.used("x_usd"), 130 * 0.005)

    def test_post_read_books_the_worst_case_before_each_page(self):
        # 0.30 left: one page of up to 100 posts (0.50) must be refused
        c = self.client([posts(range(10))], ceiling=0.30, approved=["kol_one"])
        with self.assertRaises(BudgetExceeded):
            c.user_posts("42", "kol_one", "2026-07-03T00:00:00Z", "2026-10-01T00:00:00Z")
        self.assertEqual(self.transport.urls, [])

    def test_counts_cost_one_cent_per_request_and_pages_are_summed(self):
        page1 = (200, json.dumps({"data": [{"start": "2026-09-01", "tweet_count": 3}],
                                  "meta": {"total_tweet_count": 3, "next_token": "x"}}))
        page2 = (200, json.dumps({"data": [{"start": "2026-08-01", "tweet_count": 4}],
                                  "meta": {"total_tweet_count": 4}}))
        c = self.client([page1, page2])
        days = c.counts_all("from:a -is:retweet", "2026-08-01T00:00:00Z", "2026-10-01T00:00:00Z")
        self.assertEqual(sum(d["tweet_count"] for d in days), 7)
        self.assertAlmostEqual(self.ledger.used("x_usd"), 0.02)

    def test_failed_request_raises_and_is_not_charged(self):
        c = self.client([(403, json.dumps({"title": "Forbidden"}))])
        with self.assertRaises(XError):
            c.counts_all("from:a", "2026-08-01T00:00:00Z", "2026-10-01T00:00:00Z")
        self.assertEqual(self.ledger.used("x_usd"), 0)

    def test_cached_answer_is_not_paid_twice(self):
        c = self.client([users(["a"])])
        c.users_by(["a"])
        c.users_by(["a"])
        self.assertEqual(len(self.transport.urls), 1)
        self.assertAlmostEqual(self.ledger.used("x_usd"), 0.01)

    def test_token_is_never_written_to_disk(self):
        c = self.client([users(["a"])])
        c.users_by(["a"])
        for root, _, files in os.walk(self.tmp.name):
            for name in files:
                with open(os.path.join(root, name), encoding="utf-8") as fh:
                    self.assertNotIn(TOKEN, fh.read())


class ApprovalFileTest(unittest.TestCase):
    def write(self, text):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="\n")
        tmp.write(text)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return tmp.name

    def test_only_rows_marked_approved_with_a_date_count(self):
        path = self.write("username,approved,approved_on\nAlice,yes,2026-10-03\nbob,yes,\ncarol,no,2026-10-03\n")
        self.assertEqual(load_approved(path), {"alice"})

    def test_missing_file_means_nobody_is_approved(self):
        self.assertEqual(load_approved(os.path.join(tempfile.gettempdir(), "does-not-exist-123.csv")), set())


if __name__ == "__main__":
    unittest.main()
