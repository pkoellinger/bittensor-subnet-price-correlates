import os
import tempfile
import unittest

from snprice.io import read_json, read_table, write_json, write_table


class TableTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sub", "t.csv")

    def test_missing_values_survive_a_round_trip_as_missing(self):
        write_table(self.path, [{"netuid": 1, "x": 0.5}, {"netuid": 2, "x": None}])
        rows = read_table(self.path)
        self.assertEqual(rows[0], {"netuid": "1", "x": "0.5"})
        self.assertIsNone(rows[1]["x"])

    def test_zero_is_not_missing(self):
        write_table(self.path, [{"netuid": 1, "x": 0}])
        self.assertEqual(read_table(self.path)[0]["x"], "0")

    def test_unix_line_ends_and_utf8(self):
        write_table(self.path, [{"netuid": 29, "name": "hoτfloaτ"}])
        with open(self.path, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(read_table(self.path)[0]["name"], "hoτfloaτ")

    def test_column_order_can_be_fixed_and_extra_keys_dropped(self):
        write_table(self.path, [{"b": 2, "a": 1, "c": 3}], columns=["a", "b"])
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(fh.readline().strip(), "a,b")

    def test_json_round_trip_and_default(self):
        p = os.path.join(self.tmp.name, "x", "a.json")
        self.assertEqual(read_json(p, default={}), {})
        write_json(p, {"b": 1, "a": [1, 2]})
        self.assertEqual(read_json(p), {"a": [1, 2], "b": 1})


if __name__ == "__main__":
    unittest.main()
