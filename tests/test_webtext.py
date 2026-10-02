import unittest

from snprice.webtext import (doc_links, is_blocked, is_parked, page_links, pick_pages, safe_url, same_site,
                             visible_text, windows, x_profiles)

HTML = """<!DOCTYPE html><html><head><title>Acme  Subnet</title><style>p{color:red}</style>
<script>var hidden = "do not show";</script></head>
<body><nav><a href="/docs">Docs</a> <a href="https://docs.acme.ai/api">API reference</a>
<a href="/whitepaper.pdf">White&nbsp;paper</a> <a href="#top">Top</a> <a href="mailto:hi@acme.ai">Mail</a>
<a href="https://x.com/acme">X</a> <a href="/team/">Our team</a><a href="/blog/post-1">Blog</a></nav>
<h1>Acme</h1><p>We build   things.<br>Fast.</p><noscript>enable js</noscript>
<svg><text>icon</text></svg><div>Second&amp;block</div><template>tpl</template></body></html>"""


class VisibleTextTest(unittest.TestCase):
    def test_scripts_styles_and_hidden_parts_are_dropped(self):
        text = visible_text(HTML)
        for hidden in ("do not show", "color:red", "enable js", "icon", "tpl"):
            self.assertNotIn(hidden, text)

    def test_title_and_body_text_with_line_breaks_between_blocks(self):
        text = visible_text(HTML)
        self.assertTrue(text.startswith("Acme Subnet\n"))
        self.assertIn("Acme\nWe build things.\nFast.\nSecond&block", text)

    def test_entities_and_whitespace(self):
        self.assertIn("White paper", visible_text(HTML))
        self.assertNotIn("  ", visible_text(HTML))

    def test_empty_input(self):
        self.assertEqual(visible_text(""), "")


class LinksTest(unittest.TestCase):
    def test_absolute_urls_with_anchor_text(self):
        links = page_links(HTML, "https://acme.ai/")
        self.assertIn(("https://acme.ai/docs", "Docs"), links)
        self.assertIn(("https://docs.acme.ai/api", "API reference"), links)
        self.assertIn(("https://acme.ai/whitepaper.pdf", "White paper"), links)

    def test_fragments_and_mail_links_are_dropped(self):
        urls = [u for u, _ in page_links(HTML, "https://acme.ai/")]
        self.assertFalse([u for u in urls if u.startswith("mailto:") or "#" in u])

    def test_fragment_is_removed_from_a_real_link(self):
        links = page_links('<a href="/docs#install">Install</a>', "https://acme.ai/")
        self.assertEqual(links, [("https://acme.ai/docs", "Install")])


class SameSiteTest(unittest.TestCase):
    def test_subdomains_belong_to_the_site(self):
        self.assertTrue(same_site("https://docs.acme.ai/api", "https://www.acme.ai/"))
        self.assertTrue(same_site("https://acme.ai/team", "https://acme.ai"))

    def test_other_sites(self):
        self.assertFalse(same_site("https://x.com/acme", "https://acme.ai/"))
        self.assertFalse(same_site("https://notacme.ai/", "https://acme.ai/"))

    def test_shared_hosts_are_a_site_per_subdomain(self):
        self.assertFalse(same_site("https://other.github.io/x", "https://acme.github.io/"))
        self.assertTrue(same_site("https://acme.github.io/docs", "https://acme.github.io/"))
        self.assertFalse(same_site("https://b.vercel.app/", "https://a.vercel.app/"))


class PickPagesTest(unittest.TestCase):
    def setUp(self):
        self.links = page_links(HTML, "https://acme.ai/")

    def test_pages_on_the_site_that_match_a_topic_in_priority_order(self):
        picked = pick_pages(self.links, "https://acme.ai/", limit=8)
        self.assertEqual(picked, ["https://acme.ai/docs", "https://docs.acme.ai/api", "https://acme.ai/team/"])

    def test_documents_and_other_sites_are_not_pages_to_read(self):
        picked = pick_pages(self.links, "https://acme.ai/", limit=8)
        self.assertNotIn("https://acme.ai/whitepaper.pdf", picked)
        self.assertNotIn("https://x.com/acme", picked)
        self.assertNotIn("https://acme.ai/blog/post-1", picked)

    def test_limit(self):
        self.assertEqual(pick_pages(self.links, "https://acme.ai/", limit=1), ["https://acme.ai/docs"])

    def test_home_page_itself_and_duplicates_are_skipped(self):
        links = [("https://acme.ai/", "Docs home"), ("https://acme.ai/docs", "Docs"), ("https://acme.ai/docs/", "Documentation")]
        self.assertEqual(pick_pages(links, "https://acme.ai", limit=8), ["https://acme.ai/docs"])

    def test_documentation_hosted_elsewhere_is_followed_when_the_link_says_so(self):
        links = [("https://acme.gitbook.io/acme", "Documentation"), ("https://medium.com/@acme", "Blog")]
        self.assertEqual(pick_pages(links, "https://acme.ai/", limit=8), ["https://acme.gitbook.io/acme"])


class DocLinksTest(unittest.TestCase):
    def test_pdf_and_paper_links(self):
        links = page_links(HTML, "https://acme.ai/") + [("https://arxiv.org/abs/2601.00001", "our paper"),
                                                       ("https://acme.ai/litepaper", "Litepaper"),
                                                       ("https://acme.ai/pricing", "Pricing")]
        self.assertEqual(doc_links(links), [("https://acme.ai/whitepaper.pdf", "White paper"),
                                            ("https://arxiv.org/abs/2601.00001", "our paper"),
                                            ("https://acme.ai/litepaper", "Litepaper")])


class ParkedTest(unittest.TestCase):
    def test_parking_pages(self):
        self.assertTrue(is_parked("acme.ai is for sale! Buy this domain today"))
        self.assertTrue(is_parked("This domain is parked free, courtesy of GoDaddy.com"))

    def test_real_pages(self):
        self.assertFalse(is_parked("Acme sells compute. Subnet 12 on Bittensor."))
        self.assertFalse(is_parked(""))


class WindowsTest(unittest.TestCase):
    TEXT = "a" * 300 + " Get an API key here " + "b" * 300 + " our API docs " + "c" * 300

    def test_text_around_each_match(self):
        out = windows(self.TEXT, r"\bAPI\b", radius=20)
        self.assertEqual(len(out), 2)
        self.assertIn("Get an API key here", out[0])
        self.assertLessEqual(len(out[0]), 20 + 3 + 20)

    def test_overlapping_windows_are_merged(self):
        out = windows("x API y API z", r"\bAPI\b", radius=50)
        self.assertEqual(out, ["x API y API z"])

    def test_limit_and_no_match(self):
        self.assertEqual(len(windows(self.TEXT, r"\bAPI\b", radius=20, limit=1)), 1)
        self.assertEqual(windows(self.TEXT, r"\bMCP\b", radius=20), [])


class SafeUrlTest(unittest.TestCase):
    def test_ordinary_addresses(self):
        self.assertEqual(safe_url("https://acme.ai/path?x=1"), "https://acme.ai/path?x=1")
        self.assertEqual(safe_url("http://acme.ai"), "http://acme.ai")
        self.assertEqual(safe_url(" www.yanez.ai "), "https://www.yanez.ai")
        self.assertEqual(safe_url("blockmachine.io"), "https://blockmachine.io")

    def test_text_that_is_not_a_web_address_is_refused(self):
        for bad in ("", None, "--remote-debugging-port=9222", "-x", "file:///c:/Windows/win.ini",
                    "javascript:alert(1)", "ftp://acme.ai/file", "https://", "not a url", "https://acme .ai"):
            self.assertIsNone(safe_url(bad), bad)

    def test_local_and_private_addresses_are_refused(self):
        for bad in ("http://localhost:8000", "http://127.0.0.1/", "https://192.168.1.10", "http://10.0.0.5",
                    "http://172.16.3.1", "http://[::1]/", "http://169.254.169.254/latest", "http://printer.local"):
            self.assertIsNone(safe_url(bad), bad)


class BlockedTest(unittest.TestCase):
    def test_bot_challenge_pages(self):
        self.assertTrue(is_blocked("Just a moment...\nVerifying you are human. This may take a few seconds."))
        self.assertTrue(is_blocked("Attention Required! | Cloudflare"))
        self.assertTrue(is_blocked("Access denied\nError code 1020"))

    def test_real_pages(self):
        # a long page that happens to contain the words is a real page
        self.assertFalse(is_blocked("Acme\nJust a moment of your time: sign up for our newsletter. " + "x" * 3000))
        self.assertFalse(is_blocked("Acme sells compute."))


class XProfilesTest(unittest.TestCase):
    def test_profile_links_on_x_and_twitter(self):
        links = [("https://x.com/chutes_ai", "X"), ("https://twitter.com/Bitcast_network/", "Twitter"),
                 ("https://www.x.com/webuildscore?lang=en", "")]
        self.assertEqual(x_profiles(links), ["chutes_ai", "Bitcast_network", "webuildscore"])

    def test_same_profile_linked_twice_is_listed_once(self):
        links = [("https://x.com/chutes_ai", "X"), ("https://twitter.com/Chutes_AI", "Follow us")]
        self.assertEqual(x_profiles(links), ["chutes_ai"])

    def test_share_buttons_posts_and_site_pages_are_not_profiles(self):
        links = [("https://twitter.com/intent/tweet?text=hello", "Share"), ("https://x.com/share?url=a", "Share"),
                 ("https://x.com/home", ""), ("https://x.com/search?q=tao", ""), ("https://x.com/hashtag/tao", ""),
                 ("https://x.com/i/spaces/1abc", ""), ("https://x.com/someone/status/123456", "a post"),
                 ("https://x.com/", "X"), ("https://example.com/x.com/fake", "")]
        self.assertEqual(x_profiles(links), [])

    def test_accounts_of_the_network_itself_are_not_the_subnets_account(self):
        links = [("https://x.com/opentensor", "Bittensor"), ("https://x.com/bittensor_", ""), ("https://x.com/acme_ai", "")]
        self.assertEqual(x_profiles(links), ["acme_ai"])


if __name__ == "__main__":
    unittest.main()
