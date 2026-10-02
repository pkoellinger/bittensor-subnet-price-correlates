import json
import os
import tempfile
import unittest

from snprice.fetch import BudgetExceeded, FetchError, Ledger, Taostats

KEY = "tao-secret-key:abc123"


def page(rows, total, next_page=None, current=1):
    return json.dumps({
        "pagination": {"current_page": current, "per_page": 200, "total_items": total,
                       "total_pages": 1, "next_page": next_page, "prev_page": None},
        "data": rows,
    })


class Transport:
    """Scripted HTTP transport: a list of (status, body) answers."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.urls = []
        self.headers = []

    def __call__(self, url, headers):
        self.urls.append(url)
        self.headers.append(headers)
        return self.answers.pop(0)


class TaostatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.slept = []

    def client(self, answers, ceiling=1000, tries=4):
        self.transport = Transport(answers)
        self.ledger = Ledger(os.path.join(self.tmp.name, "ledger.json"), {"taostats": ceiling})
        return Taostats(KEY, cache_dir=os.path.join(self.tmp.name, "cache"), ledger=self.ledger,
                        transport=self.transport, min_gap=0, sleep=self.slept.append, tries=tries)

    def test_rate_limit_that_never_clears_raises(self):
        c = self.client([(429, "")] * 4)
        with self.assertRaises(FetchError):
            c.get("/api/subnet/latest/v1", netuid=1)

    def test_ok_status_without_data_key_raises(self):
        c = self.client([(200, json.dumps({"message": "slow down"}))] * 4)
        with self.assertRaises(FetchError):
            c.get("/api/subnet/latest/v1", netuid=1)

    def test_unparseable_body_raises(self):
        c = self.client([(200, "<html>blocked</html>")] * 4)
        with self.assertRaises(FetchError):
            c.get("/api/subnet/latest/v1", netuid=1)

    def test_retry_after_rate_limit_then_success(self):
        c = self.client([(429, ""), (200, page([{"netuid": 1}], 1))])
        out = c.get("/api/subnet/latest/v1", netuid=1)
        self.assertEqual(out["data"], [{"netuid": 1}])
        self.assertEqual(len(self.transport.urls), 2)
        self.assertTrue(self.slept and max(self.slept) >= 10)

    def test_client_error_is_not_retried(self):
        c = self.client([(404, ""), (200, page([], 0))])
        with self.assertRaises(FetchError):
            c.get("/api/does/not/exist/v1")
        self.assertEqual(len(self.transport.urls), 1)

    def test_genuinely_empty_result_is_returned_as_empty(self):
        c = self.client([(200, page([], 0))])
        self.assertEqual(c.get("/api/transfer/v1", to="5abc")["data"], [])

    def test_second_identical_request_is_served_from_cache(self):
        c = self.client([(200, page([{"netuid": 1}], 1))])
        first = c.get("/api/subnet/latest/v1", netuid=1)
        second = c.get("/api/subnet/latest/v1", netuid=1)
        self.assertEqual(first, second)
        self.assertEqual(len(self.transport.urls), 1)

    def test_parameter_order_does_not_defeat_the_cache(self):
        c = self.client([(200, page([{"x": 1}], 1))])
        c.get("/api/transfer/v1", to="5abc", limit=50)
        c.get("/api/transfer/v1", limit=50, to="5abc")
        self.assertEqual(len(self.transport.urls), 1)

    def test_key_goes_in_the_header_and_never_to_disk(self):
        c = self.client([(200, page([{"netuid": 1}], 1))])
        c.get("/api/subnet/latest/v1", netuid=1)
        self.assertEqual(self.transport.headers[0]["Authorization"], KEY)
        self.assertNotIn(KEY, self.transport.urls[0])
        for root, _, files in os.walk(self.tmp.name):
            for name in files:
                with open(os.path.join(root, name), encoding="utf-8") as fh:
                    self.assertNotIn(KEY, fh.read(), name)

    def test_every_attempt_is_booked_in_the_ledger(self):
        c = self.client([(429, ""), (200, page([{"netuid": 1}], 1))])
        c.get("/api/subnet/latest/v1", netuid=1)
        self.assertEqual(self.ledger.used("taostats"), 2)

    def test_ceiling_stops_before_the_request_is_sent(self):
        c = self.client([(200, page([{"netuid": 1}], 1)), (200, page([{"netuid": 2}], 1))], ceiling=1)
        c.get("/api/subnet/latest/v1", netuid=1)
        with self.assertRaises(BudgetExceeded):
            c.get("/api/subnet/latest/v1", netuid=2)
        self.assertEqual(len(self.transport.urls), 1)

    def test_get_all_follows_pages(self):
        c = self.client([
            (200, page([{"i": 1}, {"i": 2}], 3, next_page=2)),
            (200, page([{"i": 3}], 3, next_page=None, current=2)),
        ])
        rows = c.get_all("/api/transfer/v1", to="5abc")
        self.assertEqual([r["i"] for r in rows], [1, 2, 3])

    def test_get_all_raises_when_fewer_rows_arrive_than_announced(self):
        c = self.client([
            (200, page([{"i": 1}, {"i": 2}], 5, next_page=2)),
            (200, page([{"i": 3}], 5, next_page=None, current=2)),
        ])
        with self.assertRaises(FetchError):
            c.get_all("/api/transfer/v1", to="5abc")

    def test_get_all_page_cap_is_an_error_unless_declared_partial(self):
        c = self.client([(200, page([{"i": 1}], 9, next_page=2))])
        with self.assertRaises(FetchError):
            c.get_all("/api/transfer/v1", to="5abc", max_pages=1)
        c = self.client([(200, page([{"i": 1}], 9, next_page=2))])
        rows = c.get_all("/api/transfer/v1", to="5abc", max_pages=1, partial_ok=True)
        self.assertEqual(len(rows), 1)


class LedgerTest(unittest.TestCase):
    def test_ledger_persists_between_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ledger.json")
            Ledger(path, {"x_usd": 50}).book("x_usd", 12.5)
            self.assertEqual(Ledger(path, {"x_usd": 50}).used("x_usd"), 12.5)

    def test_booking_over_the_ceiling_raises_and_books_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(os.path.join(tmp, "ledger.json"), {"x_usd": 50})
            ledger.book("x_usd", 49.99)
            with self.assertRaises(BudgetExceeded):
                ledger.book("x_usd", 0.02)
            self.assertAlmostEqual(ledger.used("x_usd"), 49.99)

    def test_bucket_without_ceiling_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(os.path.join(tmp, "ledger.json"), {"x_usd": 50})
            with self.assertRaises(KeyError):
                ledger.book("something_else", 1)


if __name__ == "__main__":
    unittest.main()
