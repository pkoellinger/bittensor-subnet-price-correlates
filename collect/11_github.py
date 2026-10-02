"""GitHub activity, repository statistics and the documentation checklist (Y5, Y6, Y13, E7).

Commit windows use the committer date and end at T, so they are pinned to the
snapshot. Stars, forks and the documentation files are as of collection time.

For an organisation, "org" columns cover all its public non-fork repositories. For a
personal account only the listed repository is used, because a personal account also
holds unrelated projects.

Writes
  data/intermediate/github_wave<N>.csv          one row per subnet
  data/evidence/github_repos_wave<N>.csv        repositories scanned, with commit counts and head commit at T
  data/evidence/doc_checklist_wave<N>.csv       what matched for every checklist item
"""
import base64
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.github import DOC_ITEMS, GitHub, doc_checklist, token_from_environment  # noqa: E402
from snprice.io import archive, read_table, write_table  # noqa: E402
from snprice.windows import bounds  # noqa: E402

SIBLING_PATTERN = ("miner", "validator", "subnet", "docs")
MAX_SIBLINGS = 3
SEARCH_GAP = 2.3          # the search API allows 30 requests a minute


def iso(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def epoch(text):
    return time.mktime(time.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone


def author_id(commit):
    """Stable identity of a commit author: GitHub login if known, else the e-mail."""
    if commit.get("author") and commit["author"].get("login"):
        return "login:" + commit["author"]["login"].lower()
    a = (commit.get("commit") or {}).get("author") or {}
    return "mail:" + (a.get("email") or a.get("name") or "unknown").lower()


def summarise(commits, lo, hi):
    """Commits with committer date in (lo, hi]: count, authors, active days."""
    inside = [c for c in commits if lo < epoch(c["commit"]["committer"]["date"]) <= hi]
    return {
        "n": len(inside),
        "authors": {author_id(c) for c in inside},
        "days": {c["commit"]["committer"]["date"][:10] for c in inside},
    }


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    links = read_table(paths.EVIDENCE / f"links_wave{wave}.csv")
    arch = archive()
    gh = GitHub(token_from_environment(), cache_dir=str(paths.raw_dir("github")))

    w_lo, w_hi = (arch.timestamp(b) for b in bounds(cfg, "window"))
    l_lo, l_hi = (arch.timestamp(b) for b in bounds(cfg, "lag"))
    long_lo = arch.timestamp(bounds(cfg, "window", days=cfg["long_window_days"])[0])
    print(f"windows: 30d {iso(w_lo)} to {iso(w_hi)}, lag {iso(l_lo)} to {iso(l_hi)}, 90d from {iso(long_lo)}", flush=True)

    commit_cache = {}

    def commits_of(owner, repo):
        if (owner, repo) not in commit_cache:
            commit_cache[(owner, repo)] = gh.pages(f"/repos/{owner}/{repo}/commits", since=iso(long_lo), until=iso(w_hi)) or []
        return commit_cache[(owner, repo)]

    last_search = [0.0]

    def merged_prs(scope, lo, hi):
        wait = SEARCH_GAP - (time.time() - last_search[0])
        if wait > 0:
            time.sleep(wait)
        last_search[0] = time.time()
        res = gh.get("/search/issues", q=f"{scope} is:pr is:merged merged:{iso(lo)}..{iso(hi)}", per_page=1)
        return res.get("total_count") if res else None

    out, repo_rows, doc_rows = [], [], []
    for i, link in enumerate(links, 1):
        n = int(link["netuid"])
        row = {"netuid": n, "gh_owner": link["gh_owner"], "gh_owner_type": link["gh_owner_type"],
               "gh_repo": link["gh_repo"], "gh_status": link["gh_status"]}
        if link["gh_status"] not in ("found", "owner_only"):
            out.append({**row, **{k: None for k in DOC_ITEMS}, "doc_score": None})
            continue
        owner, repo, is_org = link["gh_owner"], link["gh_repo"], link["gh_owner_type"] == "Organization"
        meta = gh.get(f"/repos/{owner}/{repo}")

        # repositories in scope
        if is_org:
            all_repos = [r for r in (gh.pages(f"/orgs/{owner}/repos", type="public") or []) if not r.get("fork")]
            scope_repos = [r["name"] for r in all_repos if (r.get("pushed_at") or "") >= iso(long_lo)]
            if repo not in scope_repos:
                scope_repos.append(repo)
            stars_org = sum(r.get("stargazers_count", 0) for r in all_repos)
        else:
            all_repos, scope_repos, stars_org = [meta], [repo], meta.get("stargazers_count", 0)

        per_repo = {name: commits_of(owner, name) for name in scope_repos}
        win = {name: summarise(c, w_lo, w_hi) for name, c in per_repo.items()}
        lag = {name: summarise(c, l_lo, l_hi) for name, c in per_repo.items()}
        long = {name: summarise(c, long_lo, w_hi) for name, c in per_repo.items()}

        def union(parts, field):
            s = set()
            for p in parts.values():
                s |= p[field]
            return s

        head = gh.get(f"/repos/{owner}/{repo}/commits", until=iso(w_hi), per_page=1) or []
        last_commit = epoch(head[0]["commit"]["committer"]["date"]) if head else None
        scope = (f"org:{owner}" if is_org else f"repo:{owner}/{repo}")

        row.update({
            "gh_commits_30d_repo": win[repo]["n"],
            "gh_commits_30d_org": sum(p["n"] for p in win.values()),
            "gh_authors_30d_org": len(union(win, "authors")),
            "gh_active_days_30d_org": len(union(win, "days")),
            "gh_prs_merged_30d_org": merged_prs(scope, w_lo, w_hi),
            "gh_commits_lag30_repo": lag[repo]["n"],
            "gh_commits_lag30_org": sum(p["n"] for p in lag.values()),
            "gh_authors_lag30_org": len(union(lag, "authors")),
            "gh_active_days_lag30_org": len(union(lag, "days")),
            "gh_prs_merged_lag30_org": merged_prs(scope, l_lo, l_hi),
            "gh_authors_90d_org": len(union(long, "authors")),
            "gh_contributors_alltime_repo": gh.count(f"/repos/{owner}/{repo}/contributors"),
            "gh_stars_repo": meta.get("stargazers_count"),
            "gh_forks_repo": meta.get("forks_count"),
            "gh_stars_org": stars_org,
            "gh_repo_age_days": (w_hi - epoch(meta["created_at"])) / 86400.0,
            "gh_days_since_push": ((w_hi - last_commit) / 86400.0) if last_commit else None,
            "gh_releases_repo": gh.count(f"/repos/{owner}/{repo}/releases"),
            "gh_repos_in_scope": len(scope_repos),
        })

        # documentation checklist: the listed repository, plus up to three sibling repositories of an
        # organisation whose name says miner, validator, subnet or docs
        siblings = [r["name"] for r in sorted(all_repos, key=lambda r: r.get("pushed_at") or "", reverse=True)
                    if r["name"] != repo and any(p in r["name"].lower() for p in SIBLING_PATTERN)][:MAX_SIBLINGS] \
            if is_org else []
        best = None
        for name in [repo] + siblings:
            rmeta = meta if name == repo else gh.get(f"/repos/{owner}/{name}")
            if not rmeta:
                continue
            profile = gh.get(f"/repos/{owner}/{name}/community/profile")
            readme = gh.get(f"/repos/{owner}/{name}/readme")
            text = base64.b64decode(readme["content"]).decode("utf-8", "replace") if readme and readme.get("content") else ""
            tree = gh.get(f"/repos/{owner}/{name}/git/trees/{rmeta['default_branch']}", recursive=1)
            tree_paths = [t["path"] for t in (tree or {}).get("tree", []) if t.get("type") == "blob"]
            check = doc_checklist(profile or {}, text, tree_paths, "",
                                  " ".join(filter(None, [rmeta.get("homepage"), link["website_url"]])))
            for item in DOC_ITEMS:
                if check[item]:
                    doc_rows.append({"netuid": n, "item": item, "repo": f"{owner}/{name}",
                                     "matched": check["evidence"].get(item, "community profile")})
            if best is None:
                best = {k: check[k] for k in DOC_ITEMS}
            else:
                best = {k: max(best[k], check[k]) for k in DOC_ITEMS}
        row.update(best)
        row["doc_score"] = sum(best.values())
        row["doc_repos_checked"] = 1 + len(siblings)
        out.append(row)

        for name in scope_repos:
            repo_rows.append({"netuid": n, "repo": f"{owner}/{name}", "is_listed_repo": int(name == repo),
                              "commits_30d": win[name]["n"], "commits_lag30": lag[name]["n"],
                              "commits_90d": long[name]["n"],
                              "head_sha_at_t": head[0]["sha"] if (name == repo and head) else None})
        if i % 10 == 0:
            print(f"  {i}/{len(links)} subnets, {gh.requests} GitHub requests", flush=True)

    write_table(paths.INTERMEDIATE / f"github_wave{wave}.csv", out)
    write_table(paths.EVIDENCE / f"github_repos_wave{wave}.csv", repo_rows)
    write_table(paths.EVIDENCE / f"doc_checklist_wave{wave}.csv", doc_rows)
    with_repo = [r for r in out if r.get("gh_commits_30d_org") is not None]
    print(f"wrote GitHub data for {len(with_repo)} subnets with a repository ({gh.requests} requests); "
          f"{len(repo_rows)} repositories scanned")


if __name__ == "__main__":
    main()
