"""Resolve each subnet's GitHub repository, website and X handle, with the source of each.

On-chain identity is incomplete (at T: GitHub for 107 of 128 subnets, a website for
103, no X handle field at all), so links are resolved in a fixed order and the source
is recorded:

  GitHub   on-chain identity -> Taostats identity -> manual
  website  on-chain identity -> Taostats identity -> repository homepage -> GitHub owner profile -> manual
  X handle Taostats identity -> GitHub owner profile -> manual

Manual entries live in data/manual/links_manual.csv (netuid, field, value, evidence_url)
and always carry an evidence URL. They are applied last and override nothing that the
chain or an API supplied unless the row says override=yes.

Writes  data/evidence/links_wave<N>.csv   one row per subnet
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.events import contact_domain, norm_name  # noqa: E402
from snprice.github import GitHub, parse_github_url, token_from_environment  # noqa: E402
from snprice.io import read_table, taostats, write_table  # noqa: E402

MANUAL = paths.MANUAL / "links_manual.csv"


def clean_url(url):
    url = (url or "").strip()
    if not url or url in ("-", "none", "None", "null"):
        return ""
    return url if "://" in url else "https://" + url


def clean_handle(handle):
    handle = (handle or "").strip().lstrip("@")
    handle = handle.rsplit("/", 1)[-1] if "/" in handle else handle
    return handle if handle and all(c.isalnum() or c == "_" for c in handle) and len(handle) <= 15 else ""


def pick_primary_repo(repos, subnet_name):
    """Owner page without a repository: prefer a repo named after the subnet, else the most starred."""
    repos = [r for r in repos if not r.get("fork") and not r.get("archived")]
    if not repos:
        return None
    key = norm_name(subnet_name)
    named = [r for r in repos if key and key in norm_name(r["name"])] or \
            [r for r in repos if "subnet" in r["name"].lower()]
    pool = named or repos
    return max(pool, key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at") or ""))["name"]


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    tao = taostats()
    gh = GitHub(token_from_environment(), cache_dir=str(paths.raw_dir("github")))
    tident = {int(r["netuid"]): r for r in tao.get("/api/subnet/identity/v1", limit=200)["data"]}
    manual = {}
    if MANUAL.exists():
        for m in read_table(MANUAL):
            manual.setdefault(int(m["netuid"]), {})[m["field"]] = m

    rows = []
    for r in roster:
        n = int(r["netuid"])
        t = tident.get(n, {})
        man = manual.get(n, {})

        # --- GitHub
        gh_url, gh_source = clean_url(r["github_repo"]), "chain_identity"
        if not gh_url:
            gh_url, gh_source = clean_url(t.get("github_repo")), "taostats_identity"
        if ("github" in man) and (not gh_url or man["github"].get("override") == "yes"):
            gh_url, gh_source = clean_url(man["github"]["value"]), "manual"
        owner, repo = parse_github_url(gh_url)
        owner_profile, repo_meta, status = None, None, "not_listed"
        if owner:
            owner_profile = gh.get(f"/users/{owner}")
            if owner_profile is None:
                status = "dead"
            else:
                owner = owner_profile["login"]
                if repo is None:
                    kind = "orgs" if owner_profile["type"] == "Organization" else "users"
                    repo = pick_primary_repo(gh.pages(f"/{kind}/{owner}/repos", type="public") or [], r["subnet_name"])
                    status = "owner_only" if repo else "dead"
                if repo:
                    repo_meta = gh.get(f"/repos/{owner}/{repo}")
                    if repo_meta is None:
                        status = "dead"
                    else:
                        owner, repo = repo_meta["owner"]["login"], repo_meta["name"]   # follows renames
                        status = "owner_only" if status == "owner_only" else "found"
        if status in ("not_listed", "dead"):
            gh_source = gh_source if status == "dead" else ""

        # --- website
        site, site_source = clean_url(r["subnet_url"]), "chain_identity"
        if not site:
            site, site_source = clean_url(t.get("subnet_url")), "taostats_identity"
        if not site and repo_meta:
            site, site_source = clean_url(repo_meta.get("homepage")), "github_repo_homepage"
        if not site and owner_profile:
            site, site_source = clean_url(owner_profile.get("blog")), "github_owner_profile"
        if ("website" in man) and (not site or man["website"].get("override") == "yes"):
            site, site_source = clean_url(man["website"]["value"]), "manual"
        if site and "github.com" in site.lower():
            site, site_source = "", ""          # a repository link is not a website

        # --- X handle
        handle, handle_source = clean_handle(t.get("twitter")), "taostats_identity"
        if not handle:
            contact = " ".join(filter(None, [r["subnet_contact"], t.get("subnet_contact")]))
            m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})", contact, flags=re.I)
            handle, handle_source = (clean_handle(m.group(1)) if m else ""), "chain_identity_contact"
        if not handle and owner_profile:
            handle, handle_source = clean_handle(owner_profile.get("twitter_username")), "github_owner_profile"
        if ("x_handle" in man) and (not handle or man["x_handle"].get("override") == "yes"):
            handle, handle_source = clean_handle(man["x_handle"]["value"]), "manual"

        rows.append({
            "netuid": n,
            "subnet_name": r["subnet_name"],
            "gh_owner": owner if status in ("found", "owner_only") else None,
            "gh_owner_type": owner_profile["type"] if owner_profile and status in ("found", "owner_only") else None,
            "gh_repo": repo if status in ("found", "owner_only") else None,
            "gh_status": status,
            "gh_source": gh_source or None,
            "gh_listed_url": gh_url or None,
            "website_url": site or None,
            "website_source": site_source if site else None,
            "x_handle": handle or None,
            "x_source": handle_source if handle else None,
            "contact_domain": contact_domain(r["subnet_contact"]) or contact_domain(t.get("subnet_contact")) or None,
            "taostats_tags": "|".join(t.get("tags") or []) or None,
            "evidence_manual": "; ".join(f"{k}: {v.get('evidence_url')}" for k, v in man.items()) or None,
        })

    write_table(paths.EVIDENCE / f"links_wave{wave}.csv", rows)
    count = lambda f: sum(1 for x in rows if f(x))  # noqa: E731
    print(f"wrote links for {len(rows)} subnets ({gh.requests} GitHub requests)")
    print("  GitHub:", {s: count(lambda x, s=s: x["gh_status"] == s) for s in ("found", "owner_only", "not_listed", "dead")})
    print("  website listed:", count(lambda x: x["website_url"]), "| X handle listed:", count(lambda x: x["x_handle"]))
    print("  X handle sources:", {s: count(lambda x, s=s: x["x_source"] == s)
                                  for s in ("taostats_identity", "chain_identity_contact", "github_owner_profile",
                                            "manual")})
    missing = [x["netuid"] for x in rows if not x["x_handle"] and x["subnet_name"]]
    print(f"  named subnets without an X handle ({len(missing)}):", missing)


if __name__ == "__main__":
    main()
