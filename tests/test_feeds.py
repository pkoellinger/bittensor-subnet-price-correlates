import json
import unittest

from snprice.feeds import parse_rss, youtube_list, youtube_watch

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Show</title>
<item><title>Subnet Session with Bob from Quantum Compute: Subnet 48</title><link>https://example.org/e1</link>
<guid isPermaLink="false">abc-1</guid><pubDate>Wed, 06 May 2026 10:00:00 GMT</pubDate><description>notes</description></item>
<item><title><![CDATA[Talking Tao & more]]></title><link>https://example.org/e2</link>
<guid>abc-2</guid><pubDate>Fri, 25 Sep 2026 22:23:00 +0100</pubDate></item>
</channel></rss>"""


def lockup(video_id, title, parts, kind="LOCKUP_CONTENT_TYPE_VIDEO"):
    rows = [{"metadataParts": [{"text": {"content": p}} for p in row]} for row in parts]
    return {"lockupViewModel": {
        "contentId": video_id, "contentType": kind,
        "metadata": {"lockupMetadataViewModel": {
            "title": {"content": title},
            "metadata": {"contentMetadataViewModel": {"metadataRows": rows}}}}}}


def page(items):
    data = {"contents": {"tabs": [{"content": {"list": items}}]}}
    return "<html><script>var ytInitialData = " + json.dumps(data) + ";</script><script>var other = {};</script></html>"


class RssTest(unittest.TestCase):
    def test_items_with_dates_in_utc(self):
        self.assertEqual(parse_rss(RSS), [
            {"episode_id": "abc-1", "title": "Subnet Session with Bob from Quantum Compute: Subnet 48",
             "published": "2026-05-06T10:00:00Z", "url": "https://example.org/e1"},
            {"episode_id": "abc-2", "title": "Talking Tao & more",
             "published": "2026-09-25T21:23:00Z", "url": "https://example.org/e2"},
        ])

    def test_link_stands_in_for_a_missing_guid(self):
        xml = RSS.replace('<guid isPermaLink="false">abc-1</guid>', "")
        self.assertEqual(parse_rss(xml)[0]["episode_id"], "https://example.org/e1")

    def test_item_without_a_date_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_rss(RSS.replace("<pubDate>Wed, 06 May 2026 10:00:00 GMT</pubDate>", ""))

    def test_feed_without_items_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_rss('<?xml version="1.0"?><rss><channel><title>x</title></channel></rss>')


class YoutubeListTest(unittest.TestCase):
    def test_videos_in_page_order(self):
        html = page([
            lockup("JQk1WVc5X8o", "Seby Rubino: Instant SN46 | Ep. 101", [["Ventura Labs"], ["217 views", "5d ago"]]),
            lockup("5wTS2RLv_QA", "Novelty Search :: Subnet 80", [["Opentensor"], ["276 views", "Streamed 6h ago"]]),
        ])
        self.assertEqual(youtube_list(html), [
            {"video_id": "JQk1WVc5X8o", "title": "Seby Rubino: Instant SN46 | Ep. 101", "age": "5d ago"},
            {"video_id": "5wTS2RLv_QA", "title": "Novelty Search :: Subnet 80", "age": "Streamed 6h ago"},
        ])

    def test_entries_that_are_not_videos_are_skipped(self):
        html = page([lockup("PL123", "A playlist", [["x"]], kind="LOCKUP_CONTENT_TYPE_PLAYLIST"),
                     lockup("abc", "A video", [["x"], ["1y ago"]])])
        self.assertEqual([v["video_id"] for v in youtube_list(html)], ["abc"])

    def test_video_without_an_age_label(self):
        self.assertEqual(youtube_list(page([lockup("abc", "A video", [["x"]])]))[0]["age"], None)

    def test_same_video_listed_twice_is_returned_once(self):
        html = page([lockup("abc", "A video", [["1y ago"]]), lockup("abc", "A video", [["1y ago"]])])
        self.assertEqual(len(youtube_list(html)), 1)

    def test_empty_list_is_allowed(self):
        self.assertEqual(youtube_list(page([])), [])

    def test_page_without_the_data_block_is_an_error(self):
        with self.assertRaises(ValueError):
            youtube_list("<html>consent required</html>")


class YoutubeWatchTest(unittest.TestCase):
    HTML = ('..."videoDetails":{"videoId":"RnCuzHiQxeE","title":"Claims Subnet 111 | Ep. 99","lengthSeconds":"3446",'
            '"channelId":"UCUvkCrx_4Kr4ZejBYrCqGoA"},..."externalChannelId":"UCUvkCrx_4Kr4ZejBYrCqGoA",'
            '"publishDate":"2026-09-03T08:00:33-07:00","ownerChannelName":"Ventura Labs",'
            '"uploadDate":"2026-09-03T08:00:33-07:00"...')

    def test_publication_time_in_utc_and_channel(self):
        self.assertEqual(youtube_watch(self.HTML),
                         {"published": "2026-09-03T15:00:33Z", "channel_id": "UCUvkCrx_4Kr4ZejBYrCqGoA"})

    def test_page_without_a_date_is_an_error(self):
        with self.assertRaises(ValueError):
            youtube_watch("<html>video unavailable</html>")


if __name__ == "__main__":
    unittest.main()
