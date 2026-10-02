"""Hand the coders their material and collect their answers (the three "by hand" steps).

    python build/coding_material.py web prepare <folder>          website facts: protocol, categories, dossiers, batches
    python build/coding_material.py web merge <folder>            -> data/manual/web_coding_wave<N>_coder_A.json, _B.json
    python build/coding_material.py whitepaper prepare <folder>   protocol section and excerpts
    python build/coding_material.py whitepaper merge <folder>     -> data/manual/whitepaper_coding_wave<N>_coder_A.json, _B.json
    python build/coding_material.py kol prepare <folder>          posts with subnets not labelled yet, one copy per coder
    python build/coding_material.py kol merge <folder>            -> data/manual/kol_polarity_wave<N>_coder_A.json, _B.json

<folder> is a working folder outside the repository: it holds texts that are not republished
(page snapshots, post texts). The briefs given to the coders are in config/coder_briefs.md.
Coders see the protocol without its results section, so that the shares found in an earlier
wave do not steer them.

Layout written by `prepare` and read by `merge`:
  web         <folder>/protocol.md, categories.md, dossiers/<netuid>.txt, batches.json,
              out/coder_A_batch_<k>.json, out/coder_B_batch_<k>.json      (answers, written by the coders)
  whitepaper  <folder>/protocol.md, excerpts.txt, out/coder_A.json, out/coder_B.json
  kol         <folder>/A/posts.json, A/criteria.md, A/labels.json and the same under B/
"""
import json
import random
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.coding import without_mailboxes  # noqa: E402
from snprice.files import atomic_write  # noqa: E402
from snprice.io import polarity_labels, read_json, read_table  # noqa: E402
from snprice.kol import LABELS  # noqa: E402

BATCH_SIZE = 22
WEB_SECTIONS = ("", "Material", "Items", "Output", "After coding", "Clarifications made in the third reading (wave 1)")
WHITEPAPER_SECTIONS = ("White paper features",)


def sections(text, wanted):
    """The named second-level sections of a Markdown text, in their order ("" = the part before the first)."""
    parts, name = {}, ""
    for line in text.splitlines(keepends=True):
        m = re.match(r"^## (.+?)\s*$", line)
        if m:
            name = m.group(1)
        parts[name] = parts.get(name, "") + line
    missing = [w for w in wanted if w not in parts]
    if missing:
        raise SystemExit(f"config/coding_protocol.md has no section {missing}")
    return "".join(parts[w] for w in wanted)


def dump(path, obj):
    """Write JSON; e-mail addresses are reduced to "@domain" (mailbox names are not republished)."""
    atomic_write(path, without_mailboxes(json.dumps(obj, indent=1, ensure_ascii=False)) + "\n")


def web_prepare(folder, wave):
    protocol = (paths.CONFIG / "coding_protocol.md").read_text(encoding="utf-8")
    (folder / "dossiers").mkdir(parents=True, exist_ok=True)
    (folder / "out").mkdir(exist_ok=True)
    atomic_write(folder / "protocol.md", sections(protocol, WEB_SECTIONS))
    shutil.copy(paths.CONFIG / "category_codebook.md", folder / "categories.md")
    netuids = sorted(int(r["netuid"]) for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv"))
    for n in netuids:
        shutil.copy(paths.raw_dir("dossiers") / f"{n}.txt", folder / "dossiers" / f"{n}.txt")
    order = netuids[:]
    random.Random(wave).shuffle(order)                 # the same batches on every run of a wave
    batches = [sorted(order[i:i + BATCH_SIZE]) for i in range(0, len(order), BATCH_SIZE)]
    dump(folder / "batches.json", batches)
    print(f"{len(netuids)} dossiers in {len(batches)} batches; both coders get the same batches (batches.json)")


def web_merge(folder, wave):
    netuids = sorted(int(r["netuid"]) for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv"))
    for coder in "AB":
        rows = []
        for path in sorted((folder / "out").glob(f"coder_{coder}_batch_*.json")):
            rows += json.loads(path.read_text(encoding="utf-8"))
        got = sorted(int(r["netuid"]) for r in rows)
        if got != netuids:
            raise SystemExit(f"coder {coder}: missing {sorted(set(netuids) - set(got))}, twice or unknown "
                             f"{sorted(n for n in set(got) if got.count(n) > 1 or n not in netuids)}")
        rows.sort(key=lambda r: int(r["netuid"]))
        dump(paths.MANUAL / f"web_coding_wave{wave}_coder_{coder}.json", rows)
        print(f"coder {coder}: {len(rows)} subnets -> data/manual/web_coding_wave{wave}_coder_{coder}.json")


def whitepaper_prepare(folder, wave):
    protocol = (paths.CONFIG / "coding_protocol.md").read_text(encoding="utf-8")
    (folder / "out").mkdir(parents=True, exist_ok=True)
    atomic_write(folder / "protocol.md", sections(protocol, WHITEPAPER_SECTIONS))
    shutil.copy(paths.raw_dir("whitepapers") / "excerpts.txt", folder / "excerpts.txt")
    blocks = (folder / "excerpts.txt").read_text(encoding="utf-8").count("=== SUBNET ")
    print(f"{blocks} white paper excerpts")


def whitepaper_merge(folder, wave):
    for coder in "AB":
        rows = json.loads((folder / "out" / f"coder_{coder}.json").read_text(encoding="utf-8"))
        rows.sort(key=lambda r: int(r["netuid"]))
        dump(paths.MANUAL / f"whitepaper_coding_wave{wave}_coder_{coder}.json", rows)
        print(f"coder {coder}: {len(rows)} white papers -> data/manual/whitepaper_coding_wave{wave}_coder_{coder}.json")


def kol_labels(wave, coder):
    return read_json(paths.MANUAL / f"kol_polarity_wave{wave}_coder_{coder}.json", default=[])


def kol_prepare(folder, wave):
    posts = read_json(paths.raw_dir("kol") / "coding_input.json")
    if posts is None:
        raise SystemExit("run `python collect/14_kol.py posts` first")
    cfg = paths.snapshot()        # labelled by both coders, in this wave or carried over from an earlier one
    done = set(polarity_labels(cfg, "A")) & set(polarity_labels(cfg, "B"))
    todo = []
    for p in posts:      # neither the account nor the way the subnet was matched is shown to the coders
        pairs = [s for s in p["subnets"] if (str(p["post_id"]), int(s["netuid"])) not in done]
        if pairs:
            todo.append({"post_id": str(p["post_id"]), "text": p["text"],
                         "subnets": [{"netuid": int(s["netuid"]), "name": s["name"]} for s in pairs]})
    for coder in "AB":
        (folder / coder).mkdir(parents=True, exist_ok=True)
        dump(folder / coder / "posts.json", todo)
        shutil.copy(paths.CONFIG / "polarity_criteria.md", folder / coder / "criteria.md")
    print(f"{len(todo)} posts with {sum(len(t['subnets']) for t in todo)} pairs still to label, in {folder}")


def kol_merge(folder, wave):
    for coder in "AB":
        asked = {(p["post_id"], s["netuid"]) for p in json.loads((folder / coder / "posts.json").read_text(encoding="utf-8"))
                 for s in p["subnets"]}
        new = json.loads((folder / coder / "labels.json").read_text(encoding="utf-8"))
        got = {}
        for r in new:
            if r["label"] not in LABELS:
                raise SystemExit(f"coder {coder}: unknown label {r['label']!r}")
            got[(str(r["post_id"]), int(r["netuid"]))] = r["label"]
        if set(got) != asked or len(new) != len(asked):
            raise SystemExit(f"coder {coder}: {len(asked - set(got))} pairs without a label, "
                             f"{len(set(got) - asked)} labels for pairs that were not asked, {len(new) - len(got)} given twice")
        merged = {(str(r["post_id"]), int(r["netuid"])): r["label"] for r in kol_labels(wave, coder)}
        merged.update(got)
        rows = [{"post_id": p, "netuid": n, "label": label} for (p, n), label in sorted(merged.items())]
        dump(paths.MANUAL / f"kol_polarity_wave{wave}_coder_{coder}.json", rows)
        print(f"coder {coder}: {len(got)} new labels, {len(rows)} in data/manual/kol_polarity_wave{wave}_coder_{coder}.json")


STEPS = {("web", "prepare"): web_prepare, ("web", "merge"): web_merge,
         ("whitepaper", "prepare"): whitepaper_prepare, ("whitepaper", "merge"): whitepaper_merge,
         ("kol", "prepare"): kol_prepare, ("kol", "merge"): kol_merge}

if __name__ == "__main__":
    if len(sys.argv) != 4 or (sys.argv[1], sys.argv[2]) not in STEPS:
        raise SystemExit(__doc__)
    target = Path(sys.argv[3]).resolve()
    if paths.ROOT in target.parents or target == paths.ROOT:
        raise SystemExit("the working folder must lie outside the repository: it holds texts that are not republished")
    STEPS[(sys.argv[1], sys.argv[2])](target, paths.snapshot()["wave"])
