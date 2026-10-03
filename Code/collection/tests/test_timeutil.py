import unittest

from snprice.timeutil import epoch, iso

SUMMER = 1789473600     # 2026-09-15 12:00:00 UTC (daylight saving time in Europe and the US)
WINTER = 1768478400     # 2026-01-15 12:00:00 UTC


class EpochTest(unittest.TestCase):
    def test_utc_timestamp_in_summer_and_winter(self):
        # a conversion that goes through local time is one hour off in one of the two
        self.assertEqual(epoch("2026-09-15T12:00:00Z"), SUMMER)
        self.assertEqual(epoch("2026-01-15T12:00:00Z"), WINTER)

    def test_accepted_spellings(self):
        for text in ("2026-09-15 12:00:00", "2026-09-15T12:00:00", "2026-09-15T12:00:00.000Z",
                     "2026-09-15T12:00:00.123456", "2026-09-15T12:00:00+00:00"):
            self.assertEqual(epoch(text), SUMMER, text)

    def test_other_time_zones_are_refused(self):
        with self.assertRaises(ValueError):
            epoch("2026-09-15T12:00:00-07:00")

    def test_garbage_is_refused(self):
        with self.assertRaises(ValueError):
            epoch("15 Sep 2026")


class IsoTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(iso(SUMMER), "2026-09-15T12:00:00Z")
        self.assertEqual(iso(WINTER + 0.9), "2026-01-15T12:00:00Z")

    def test_round_trip(self):
        self.assertEqual(epoch(iso(SUMMER)), SUMMER)


if __name__ == "__main__":
    unittest.main()
