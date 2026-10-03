import unittest

from snprice.whitepaper import choose_document, equation_lines, has_reference_list, raw_github


class ChooseDocumentTest(unittest.TestCase):
    def test_pdf_named_by_a_coder_is_the_document(self):
        self.assertEqual(choose_document(["https://b1m.ai/docs/BEAM_Whitepaper.pdf"], []),
                         "https://b1m.ai/docs/BEAM_Whitepaper.pdf")

    def test_pdf_version_offered_next_to_a_web_page_is_preferred(self):
        links = [("https://claims111.ai/papers/roessler-2026-verification.pdf", "Read"),
                 ("https://claims111.ai/papers/claims-sn111-white-paper.pdf", "Read")]
        self.assertEqual(choose_document(["https://claims111.ai/whitepaper"], links),
                         "https://claims111.ai/papers/claims-sn111-white-paper.pdf")

    def test_pdf_of_another_document_is_not_the_white_paper(self):
        links = [("https://oroagents.com/papers/oro-trajectory-paper.pdf", "Download Paper (PDF)")]
        self.assertEqual(choose_document(["https://oroagents.com/whitepaper"], links), "https://oroagents.com/whitepaper")

    def test_pdf_on_another_site_is_not_the_white_paper(self):
        links = [("https://www.bittensor.com/whitepaper.pdf", "Bittensor whitepaper")]
        self.assertEqual(choose_document(["https://acme.ai/whitepaper"], links), "https://acme.ai/whitepaper")

    def test_two_coders_naming_page_and_pdf(self):
        self.assertEqual(choose_document(["https://connito.ai/whitepaper", "https://connito.ai/Connito-Whitepaper-v1.pdf"], []),
                         "https://connito.ai/Connito-Whitepaper-v1.pdf")

    def test_relative_or_missing_addresses_are_skipped(self):
        self.assertEqual(choose_document(["whitepaper/UMI-Whitepaper.pdf", None,
                                          "https://github.com/Umi-BitSign/umi/blob/HEAD/whitepaper/UMI-Whitepaper.pdf"], []),
                         "https://github.com/Umi-BitSign/umi/blob/HEAD/whitepaper/UMI-Whitepaper.pdf")
        self.assertIsNone(choose_document([None, ""], []))


class RawGithubTest(unittest.TestCase):
    def test_blob_page_becomes_the_file_itself(self):
        self.assertEqual(raw_github("https://github.com/CortexLM/cortex/blob/main/docs/WHITEPAPER.md"),
                         "https://raw.githubusercontent.com/CortexLM/cortex/main/docs/WHITEPAPER.md")

    def test_other_addresses_are_unchanged(self):
        self.assertEqual(raw_github("https://acme.ai/whitepaper.pdf"), "https://acme.ai/whitepaper.pdf")


class ReferenceListTest(unittest.TestCase):
    def test_heading_followed_by_entries(self):
        text = "Intro\n" * 50 + "References\n[1] Nakamoto, S. Bitcoin. 2008.\n[2] Rao, Y. Bittensor. 2021.\n"
        self.assertTrue(has_reference_list(text))
        text = "Intro\n" * 50 + "7. Bibliography\nNakamoto, S. (2008). Bitcoin.\n"
        self.assertTrue(has_reference_list(text))

    def test_word_in_running_text_is_not_a_reference_list(self):
        self.assertFalse(has_reference_list("See the references in our docs for details.\n" * 30))

    def test_heading_at_the_very_start_is_a_table_of_contents(self):
        self.assertFalse(has_reference_list("Contents\nIntroduction\nReferences\n" + "Body text\n" * 200))


class EquationLinesTest(unittest.TestCase):
    def test_lines_with_formulas(self):
        text = "The score is\nS_i = sum_j w_j * r_ij\nand rewards are\nR = α · S / Σ S\nPlain sentence here."
        out = equation_lines(text)
        self.assertIn("S_i = sum_j w_j * r_ij", out)
        self.assertIn("R = α · S / Σ S", out)
        self.assertNotIn("Plain sentence here.", out)

    def test_ordinary_text_with_an_equals_sign_is_not_a_formula(self):
        self.assertEqual(equation_lines("Settings: mode = production and region = eu for all users of the service."), [])

    def test_limit_and_duplicates(self):
        text = "\n".join(["x_i = a_i + b_i"] * 5 + [f"y_{k} = x_{k} / n" for k in range(30)])
        out = equation_lines(text, limit=10)
        self.assertEqual(len(out), 10)
        self.assertEqual(len(set(out)), 10)


if __name__ == "__main__":
    unittest.main()
