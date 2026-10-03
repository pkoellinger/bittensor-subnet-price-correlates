import json
import os
import tempfile
import unittest

from snprice.github import GitHub, GitHubError, doc_checklist, parse_github_url

TOKEN = "ghp_secret_token_value"


class Transport:
    def __init__(self, answers):
        self.answers = list(answers)
        self.urls = []

    def __call__(self, url, headers):
        self.urls.append(url)
        return self.answers.pop(0)


def ok(body, link=None, remaining="4000"):
    headers = {"x-ratelimit-remaining": remaining, "x-ratelimit-reset": "100"}
    if link:
        headers["link"] = link
    return 200, headers, json.dumps(body)


class ParseUrlTest(unittest.TestCase):
    def test_owner_and_repo(self):
        self.assertEqual(parse_github_url("https://github.com/chutesai/chutes"), ("chutesai", "chutes"))

    def test_trailing_parts_are_ignored(self):
        self.assertEqual(parse_github_url("https://github.com/entrius/gittensor/tree/main"), ("entrius", "gittensor"))
        self.assertEqual(parse_github_url("https://github.com/taostat/blockmachine/"), ("taostat", "blockmachine"))
        self.assertEqual(parse_github_url("https://github.com/a/b.git"), ("a", "b"))

    def test_org_listing_has_no_repo(self):
        self.assertEqual(parse_github_url("https://github.com/orgs/Beam-Network/repositories"), ("Beam-Network", None))

    def test_owner_only(self):
        self.assertEqual(parse_github_url("https://github.com/CookingTao"), ("CookingTao", None))

    def test_not_github(self):
        self.assertEqual(parse_github_url("https://gitlab.com/a/b"), (None, None))
        self.assertEqual(parse_github_url(""), (None, None))
        self.assertEqual(parse_github_url(None), (None, None))

    def test_placeholder_repo(self):
        self.assertEqual(parse_github_url("https://github.com/deprecated/deprecated"), ("deprecated", "deprecated"))


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.slept = []

    def client(self, answers, now=0):
        self.transport = Transport(answers)
        return GitHub(TOKEN, cache_dir=self.tmp.name, transport=self.transport,
                      sleep=self.slept.append, clock=lambda: now)

    def test_get_returns_parsed_json_and_caches(self):
        c = self.client([ok({"stargazers_count": 90})])
        self.assertEqual(c.get("/repos/a/b")["stargazers_count"], 90)
        self.assertEqual(c.get("/repos/a/b")["stargazers_count"], 90)
        self.assertEqual(len(self.transport.urls), 1)

    def test_missing_resource_is_none_not_an_error(self):
        c = self.client([(404, {}, json.dumps({"message": "Not Found"}))])
        self.assertIsNone(c.get("/repos/a/missing"))

    def test_missing_resource_is_cached_too(self):
        c = self.client([(404, {}, "{}")])
        c.get("/repos/a/missing")
        self.assertIsNone(c.get("/repos/a/missing"))
        self.assertEqual(len(self.transport.urls), 1)

    def test_server_error_raises(self):
        c = self.client([(500, {}, "oops")] * 5)
        with self.assertRaises(GitHubError):
            c.get("/repos/a/b")

    def test_rate_limit_waits_until_reset_then_retries(self):
        limited = (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "160"},
                   json.dumps({"message": "API rate limit exceeded"}))
        c = self.client([limited, ok({"id": 1})], now=100)
        self.assertEqual(c.get("/repos/a/b"), {"id": 1})
        self.assertTrue(any(s >= 60 for s in self.slept))

    def test_pages_follow_the_next_link(self):
        c = self.client([
            ok([{"sha": "1"}, {"sha": "2"}], link='<https://api.github.com/repositories/1/commits?page=2>; rel="next", '
                                                  '<https://api.github.com/repositories/1/commits?page=3>; rel="last"'),
            ok([{"sha": "3"}]),
        ])
        rows = c.pages("/repos/a/b/commits", since="2026-09-01T00:00:00Z")
        self.assertEqual([r["sha"] for r in rows], ["1", "2", "3"])
        self.assertEqual(self.transport.urls[1], "https://api.github.com/repositories/1/commits?page=2")

    def test_count_reads_the_last_page_number(self):
        c = self.client([ok([{"login": "x"}], link='<https://api.github.com/r/contributors?per_page=1&page=2>; rel="next", '
                                                    '<https://api.github.com/r/contributors?per_page=1&page=47>; rel="last"')])
        self.assertEqual(c.count("/repos/a/b/contributors"), 47)

    def test_count_without_link_header_is_the_length_of_the_page(self):
        c = self.client([ok([{"login": "x"}])])
        self.assertEqual(c.count("/repos/a/b/contributors"), 1)
        c = self.client([ok([])])
        self.assertEqual(c.count("/repos/a/c/contributors"), 0)

    def test_count_of_missing_repo_is_none(self):
        c = self.client([(404, {}, "{}")])
        self.assertIsNone(c.count("/repos/a/missing/contributors"))

    def test_token_goes_in_header_and_never_to_disk(self):
        c = self.client([ok({"id": 1})])
        c.get("/repos/a/b")
        for root, _, files in os.walk(self.tmp.name):
            for name in files:
                with open(os.path.join(root, name), encoding="utf-8") as fh:
                    self.assertNotIn(TOKEN, fh.read())


class DocChecklistTest(unittest.TestCase):
    PROFILE = {"files": {"readme": {"url": "x"}, "license": {"spdx_id": "MIT"}, "contributing": None}}

    def test_headings_and_paths_are_detected(self):
        readme = "# IOTA\n## Installation\n## Additional Miner Documentation\n## Compute Requirements\n" + "x" * 600
        paths = ["docs/validator.md", "README.md", "LICENSE", "src/main.py"]
        out = doc_checklist(self.PROFILE, readme, paths, website_text="", homepage="")
        self.assertEqual(out["doc_readme"], 1)
        self.assertEqual(out["doc_license"], 1)
        self.assertEqual(out["doc_contributing"], 0)
        self.assertEqual(out["doc_miner_guide"], 1)
        self.assertEqual(out["doc_validator_guide"], 1)
        self.assertEqual(out["doc_requirements"], 1)
        self.assertEqual(out["doc_incentive_desc"], 0)
        self.assertEqual(out["doc_score"], 5)

    def test_short_readme_does_not_count(self):
        out = doc_checklist({"files": {"readme": {"url": "x"}}}, "# Title\n", [], "", "")
        self.assertEqual(out["doc_readme"], 0)

    def test_incentive_description_in_a_heading_or_a_file(self):
        out = doc_checklist(self.PROFILE, "# X\n## Incentive Mechanism\n" + "y" * 600, [], "", "")
        self.assertEqual(out["doc_incentive_desc"], 1)
        out = doc_checklist(self.PROFILE, "# X\n" + "y" * 600, ["docs/scoring.md"], "", "")
        self.assertEqual(out["doc_incentive_desc"], 1)

    def test_word_in_body_text_is_not_enough(self):
        out = doc_checklist(self.PROFILE, "# X\nminers and validators are welcome\n" + "y" * 600, [], "", "")
        self.assertEqual(out["doc_miner_guide"], 0)
        self.assertEqual(out["doc_validator_guide"], 0)

    def test_docs_site_from_homepage_or_readme_link(self):
        self.assertEqual(doc_checklist(self.PROFILE, "x" * 600, [], "", "https://docs.chutes.ai")["doc_site"], 1)
        readme = "# X\nSee https://myproject.gitbook.io/docs for details\n" + "x" * 600
        self.assertEqual(doc_checklist(self.PROFILE, readme, [], "", "")["doc_site"], 1)
        self.assertEqual(doc_checklist(self.PROFILE, "x" * 600, [], "", "https://chutes.ai")["doc_site"], 0)

    # --- rules corrected after the hand check of 15 repositories (data/manual/doc_checklist_hand_check.json)
    def test_docs_of_bittensor_or_of_tools_are_not_the_projects_docs_site(self):
        for link in ("https://docs.bittensor.com/miners", "https://docs.learnbittensor.org/subnets",
                     "https://docs.github.com/en/actions", "https://docs.docker.com/get-docker/",
                     "https://docs.python.org/3/", "https://docs.taostats.io/"):
            readme = f"# X\nSee {link} for details\n" + "x" * 600
            self.assertEqual(doc_checklist(self.PROFILE, readme, [], "", "")["doc_site"], 0, link)

    def test_own_docs_site_is_found_even_when_bittensor_docs_are_linked_first(self):
        readme = "# X\nRead https://docs.bittensor.com first, then https://docs.acme.ai/start\n" + "x" * 600
        out = doc_checklist(self.PROFILE, readme, [], "", "")
        self.assertEqual(out["doc_site"], 1)
        self.assertIn("docs.acme.ai", out["evidence"]["doc_site"])

    def test_contributing_guide_outside_the_standard_place(self):
        for paths in (["contrib/CONTRIBUTING.md"], ["docs/contribution.md"], ["docs/contributing-guide.rst"]):
            self.assertEqual(doc_checklist(self.PROFILE, "x" * 600, paths, "", "")["doc_contributing"], 1, paths)
        for heading in ("## Contribution Guidelines", "## Contributing & License"):
            readme = f"# X\n{heading}\n" + "x" * 600
            self.assertEqual(doc_checklist(self.PROFILE, readme, [], "", "")["doc_contributing"], 1, heading)

    def test_files_that_merely_contain_the_word_are_not_a_contributing_guide(self):
        paths = ["docs/MODEL_CONTRIBUTION_TERMS.md", "src/contributions.py"]
        self.assertEqual(doc_checklist(self.PROFILE, "x" * 600, paths, "", "")["doc_contributing"], 0)

    def test_heading_about_emissions_is_an_incentive_description(self):
        readme = "# X\n### How participant miner emission works\n" + "y" * 600
        self.assertEqual(doc_checklist(self.PROFILE, readme, [], "", "")["doc_incentive_desc"], 1)

    def test_no_repo_gives_missing_values(self):
        out = doc_checklist(None, None, None, "", "")
        self.assertIsNone(out["doc_score"])
        self.assertIsNone(out["doc_readme"])

    def test_evidence_names_what_matched(self):
        out = doc_checklist(self.PROFILE, "# X\n## Mining guide\n" + "y" * 600, ["docs/validator_setup.md"], "", "")
        self.assertIn("Mining guide", out["evidence"]["doc_miner_guide"])
        self.assertIn("docs/validator_setup.md", out["evidence"]["doc_validator_guide"])


if __name__ == "__main__":
    unittest.main()
