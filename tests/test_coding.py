import unittest

from snprice.coding import ITEMS, check_answer, cohen_kappa, quote_found, settle, without_mailboxes

SOURCES = {
    "https://acme.ai": "Acme\nGet an API key and call the endpoint.\nSign up  today",
    "README": "# Acme\nMiners run the node.",
    "onchain": "Acme serverless compute",
}


class QuoteFoundTest(unittest.TestCase):
    def test_verbatim_quote(self):
        self.assertTrue(quote_found("Get an API key", SOURCES["https://acme.ai"]))

    def test_line_breaks_and_runs_of_spaces_do_not_matter(self):
        self.assertTrue(quote_found("call the endpoint. Sign up today", SOURCES["https://acme.ai"]))

    def test_paraphrase_or_other_case_is_not_found(self):
        self.assertFalse(quote_found("Obtain an API key", SOURCES["https://acme.ai"]))
        self.assertFalse(quote_found("get an api key", SOURCES["https://acme.ai"]))

    def test_empty_quote_is_not_evidence(self):
        self.assertFalse(quote_found("", SOURCES["README"]))
        self.assertFalse(quote_found(None, SOURCES["README"]))
        self.assertFalse(quote_found("   ", SOURCES["README"]))

    # mailbox names are not republished: a stored quote keeps only "@domain" of an e-mail address
    PAGE_WITH_MAIL = "Authors: Jane Doe jane.doe@acme.ai · John Roe john@acme.ai"

    def test_quote_without_mailbox_names_matches_the_page(self):
        self.assertTrue(quote_found("Jane Doe @acme.ai · John Roe @acme.ai", self.PAGE_WITH_MAIL))

    def test_quote_with_the_full_address_still_matches(self):
        self.assertTrue(quote_found("Jane Doe jane.doe@acme.ai", self.PAGE_WITH_MAIL))

    def test_another_domain_does_not_match(self):
        self.assertFalse(quote_found("Jane Doe @other.ai", self.PAGE_WITH_MAIL))

    def test_stored_quotes_carry_no_mailbox_name(self):
        self.assertEqual(without_mailboxes("Jane Doe jane.doe@acme.ai"), "Jane Doe @acme.ai")
        self.assertEqual(without_mailboxes("no address here"), "no address here")
        self.assertIsNone(without_mailboxes(None))


class CheckAnswerTest(unittest.TestCase):
    def test_yes_with_a_quote_on_the_cited_page(self):
        answer = {"value": 1, "url": "https://acme.ai", "quote": "Get an API key"}
        self.assertEqual(check_answer(answer, SOURCES), "verified")

    def test_no_needs_no_evidence(self):
        self.assertEqual(check_answer({"value": 0, "url": None, "quote": None}, SOURCES), "verified")

    def test_yes_with_a_quote_that_is_on_another_page(self):
        answer = {"value": 1, "url": "README", "quote": "Get an API key"}
        self.assertEqual(check_answer(answer, SOURCES), "quote not on the cited page")

    def test_yes_citing_a_page_that_was_not_in_the_dossier(self):
        answer = {"value": 1, "url": "https://acme.ai/docs", "quote": "Get an API key"}
        self.assertEqual(check_answer(answer, SOURCES), "page not in the dossier")

    def test_yes_without_evidence(self):
        self.assertEqual(check_answer({"value": 1, "url": None, "quote": None}, SOURCES), "no evidence given")

    def test_quote_longer_than_allowed(self):
        long_sources = {"README": "x" * 400}
        self.assertEqual(check_answer({"value": 1, "url": "README", "quote": "x" * 201}, long_sources), "quote too long")

    def test_category_is_checked_like_a_yes(self):
        answer = {"value": "AI Inference & Model Serving", "url": "onchain", "quote": "serverless compute"}
        self.assertEqual(check_answer(answer, SOURCES), "verified")

    def test_trailing_slash_in_the_address_does_not_matter(self):
        answer = {"value": 1, "url": "https://acme.ai/", "quote": "Sign up"}
        self.assertEqual(check_answer(answer, SOURCES), "verified")


class KappaTest(unittest.TestCase):
    def test_perfect_agreement(self):
        self.assertAlmostEqual(cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]), 1.0)

    def test_agreement_no_better_than_chance(self):
        self.assertAlmostEqual(cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0]), 0.0)

    def test_known_value(self):
        # 20 cases: both yes 9, both no 7, a yes / b no 3, a no / b yes 1
        a = [1] * 9 + [0] * 7 + [1] * 3 + [0] * 1
        b = [1] * 9 + [0] * 7 + [0] * 3 + [1] * 1
        # observed 0.8; expected 0.6*0.5 + 0.4*0.5 = 0.5; kappa 0.6
        self.assertAlmostEqual(cohen_kappa(a, b), 0.6)

    def test_categories(self):
        self.assertAlmostEqual(cohen_kappa(["x", "y", "z"], ["x", "y", "z"]), 1.0)

    def test_no_variation_at_all_has_no_kappa(self):
        self.assertIsNone(cohen_kappa([0, 0, 0], [0, 0, 0]))

    def test_unequal_lengths_are_an_error(self):
        with self.assertRaises(ValueError):
            cohen_kappa([1], [1, 0])


class SettleTest(unittest.TestCase):
    def test_agreement_stands(self):
        self.assertEqual(settle(1, "verified", 1, "verified", None), (1, "both coders"))
        self.assertEqual(settle(0, "verified", 0, "verified", None), (0, "both coders"))

    def test_disagreement_needs_the_third_reading(self):
        self.assertEqual(settle(1, "verified", 0, "verified", None), (None, "open"))
        self.assertEqual(settle(1, "verified", 0, "verified", 1), (1, "third reading"))
        self.assertEqual(settle(1, "verified", 0, "verified", 0), (0, "third reading"))

    def test_unverified_yes_counts_as_a_disagreement_even_if_both_say_yes(self):
        self.assertEqual(settle(1, "quote not on the cited page", 1, "verified", None), (None, "open"))
        self.assertEqual(settle(1, "quote not on the cited page", 1, "verified", 1), (1, "third reading"))

    def test_third_reading_can_leave_it_missing(self):
        self.assertEqual(settle(1, "verified", 0, "verified", "NA"), (None, "third reading: not settled"))

    def test_items(self):
        self.assertEqual(ITEMS, ("whitepaper_available", "api_public", "mcp_server", "team_named", "product_live",
                                 "category"))


if __name__ == "__main__":
    unittest.main()
