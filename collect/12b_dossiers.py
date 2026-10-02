"""Dossiers for the coding step (config/coding_protocol.md): one text file per subnet.

A dossier holds only what the subnet itself publishes: on-chain name and description, the
start of the home page and of the README, passages around fixed keywords from every saved
page, links to documents, document-like files in the repository, and the names of the
owner's repositories. Coders read the dossier and nothing else, so they see no prices.

Reads   website snapshots (collect/12_web.py), cached GitHub answers (collect/11_github.py)
Writes  data/raw/wave<N>/dossiers/<netuid>.txt           the dossier
        data/raw/wave<N>/dossiers/<netuid>.sources.json  the full texts the quotes are checked against
        data/evidence/dossiers_wave<N>.csv               size and hash of every dossier
"""
import base64
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.github import GitHub, token_from_environment  # noqa: E402
from snprice.files import atomic_write  # noqa: E402
from snprice.io import read_json, read_table, write_json, write_table  # noqa: E402
from snprice.webtext import windows  # noqa: E402

HOME_HEAD = 3000
README_HEAD = 2500
RADIUS = 220
PER_ITEM = 6
PER_PAGE = 2
KEYWORDS = (
    ("white paper", r"white[\s\-]?paper|lite[\s\-]?paper|yellow[\s\-]?paper|technical paper|arxiv|\.pdf\b"),
    ("API", r"\bAPIs?\b|\bSDK\b|\bendpoints?\b|OpenAI[\s\-]compatible|api[\s\-]key"),
    ("MCP", r"\bMCP\b|model context protocol"),
    ("team", r"\bfounders?\b|co-?founder|\bCEO\b|\bCTO\b|\bour team\b|\bteam\b|linkedin"),
    ("product", r"sign[\s\-]?up|sign[\s\-]?in|log[\s\-]?in|launch app|get started|pricing|playground|download|"
                r"try (?:it|now)|waitlist|coming soon|early access|request (?:a )?demo|book a demo"),
)
DOCUMENT_FILE = re.compile(r"(white|lite|yellow)[\s_\-]?paper|\.pdf$", re.I)


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    roster = {int(r["netuid"]): r for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")}
    links = {int(l["netuid"]): l for l in read_table(paths.EVIDENCE / f"links_wave{wave}.csv")}
    web = {int(w["netuid"]): w for w in read_table(paths.INTERMEDIATE / f"web_wave{wave}.csv")}
    gh = GitHub(token_from_environment(), cache_dir=str(paths.raw_dir("github")))
    raw_web = paths.raw_dir("web")
    out_dir = paths.raw_dir("dossiers")
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for n in sorted(roster):
        r, link = roster[n], links[n]
        sources = {"onchain": " ".join(filter(None, [r["subnet_name"], r["description"]]))}
        labels = []                                   # (label, address, text)

        site = read_json(raw_web / str(n) / "pages.json") or {"pages": [], "documents": []}
        for p in site["pages"]:
            text = (raw_web / str(n) / f"{p['page']:02d}.txt").read_text(encoding="utf-8")
            if text:
                sources[p["url"]] = text
                labels.append((f"P{p['page']}", p["url"], text))

        readme, doc_files, repo_names, repo = "", [], [], None
        if link["gh_status"] in ("found", "owner_only"):
            owner, name = link["gh_owner"], link["gh_repo"]
            repo = f"{owner}/{name}"
            meta = gh.get(f"/repos/{owner}/{name}")
            answer = gh.get(f"/repos/{owner}/{name}/readme")
            if answer and answer.get("content"):
                readme = base64.b64decode(answer["content"]).decode("utf-8", "replace")
            if meta:
                tree = gh.get(f"/repos/{owner}/{name}/git/trees/{meta['default_branch']}", recursive=1)
                doc_files = [t["path"] for t in (tree or {}).get("tree", [])
                             if t.get("type") == "blob" and DOCUMENT_FILE.search(t["path"])][:15]
            if link["gh_owner_type"] == "Organization":
                repo_names = [x["name"] for x in (gh.pages(f"/orgs/{owner}/repos", type="public") or [])
                              if not x.get("fork")][:40]
        if readme:
            sources["README"] = readme
            labels.append(("README", "README", readme))

        lines = [f"SUBNET {n}: {r['subnet_name'] or '(no name)'}",
                 f"On-chain description: {r['description'] or '(none)'}",
                 f"Website: {link['website_url'] or '(none found)'} ({web[n]['website_status']})",
                 f"Main repository: {('https://github.com/' + repo) if repo else '(none found)'}", ""]
        if not labels and not r["description"]:
            lines.append("NO MATERIAL")
        else:
            lines.append("PAGES AVAILABLE (cite a page by its address, the README as README, the description as onchain)")
            lines += [f"[{label}] {address} ({len(text)} characters)" for label, address, text in labels]
            home = next((t for label, _, t in labels if label == "P0"), "")
            if home:
                lines += ["", f"HOME PAGE, FIRST {HOME_HEAD} CHARACTERS [P0]", home[:HOME_HEAD]]
            if readme:
                lines += ["", f"README, FIRST {README_HEAD} CHARACTERS", readme[:README_HEAD]]
            for topic, pattern in KEYWORDS:
                found = []
                for label, address, text in labels:
                    for passage in windows(text, pattern, radius=RADIUS, limit=PER_PAGE):
                        if len(found) < PER_ITEM:
                            found.append(f"[{label} {address}] ...{passage}...")
                lines += ["", f"PASSAGES ABOUT: {topic}"] + (found or ["(nothing found on any page)"])
            lines += ["", "LINKS TO DOCUMENTS FOUND ON THE SITE (label | address | found on)"]
            lines += [f"{d['label'] or '(no label)'} | {d['url']} | {d['found_on']}" for d in site["documents"][:15]] \
                or ["(none)"]
            lines += ["", "FILES IN THE MAIN REPOSITORY THAT LOOK LIKE DOCUMENTS"] + (doc_files or ["(none)"])
            lines += ["", "PUBLIC REPOSITORIES OF THE OWNER", ", ".join(repo_names) or "(not an organisation, or none)"]

        text = "\n".join(lines) + "\n"
        atomic_write(out_dir / f"{n}.txt", text)
        write_json(out_dir / f"{n}.sources.json", sources)
        manifest.append({"netuid": n, "chars": len(text), "pages": len([l for l in labels if l[0] != "README"]),
                         "has_readme": int(bool(readme)), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})

    write_table(paths.EVIDENCE / f"dossiers_wave{wave}.csv", manifest)
    sizes = sorted(m["chars"] for m in manifest)
    print(f"wrote {len(manifest)} dossiers; characters: median {sizes[len(sizes) // 2]}, max {sizes[-1]}, "
          f"total {sum(sizes)}; without pages and README: "
          f"{sum(1 for m in manifest if not m['pages'] and not m['has_readme'])}")


if __name__ == "__main__":
    main()
