"""Hand the coders their material and collect their answers (the three "by hand" steps).

    python build/coding_material.py web prepare <folder>          website facts: protocol, categories, dossiers, batches
    python build/coding_material.py web prepare <folder> 120 89   the same for single subnets (a site that was read later)
    python build/coding_material.py web merge <folder>            -> data/manual/web_coding_wave<N>_coder_A.json, _B.json
    python build/coding_material.py whitepaper prepare <folder>   protocol section and excerpts
    python build/coding_material.py whitepaper merge <folder>     -> data/manual/whitepaper_coding_wave<N>_coder_A.json, _B.json
    python build/coding_material.py kol prepare <folder>          posts with subnets not labelled yet, in batches, one copy per coder
    python build/coding_material.py kol merge <folder>            -> data/manual/kol_polarity_wave<N>_coder_A.json, _B.json
    python build/coding_material.py attribution prepare <folder>  posts that name a subnet by number alone, one copy per reader
    python build/coding_material.py attribution merge <folder>    -> data/manual/kol_attribution_wave<N>_reader_A.json, _B.json

<folder> is a working folder outside the repository: it holds texts that are not republished
(page snapshots, post texts). The briefs given to the coders are in config/coder_briefs.md.
Coders see the protocol without its results section, so that the shares found in an earlier
wave do not steer them.

Layout written by `prepare` and read by `merge`:
  web         <folder>/protocol.md, categories.md, dossiers/<netuid>.txt, batches.json,
              out/coder_A_batch_<k>.json, out/coder_B_batch_<k>.json      (answers, written by the coders)
  whitepaper  <folder>/protocol.md, excerpts.txt, out/coder_A.json, out/coder_B.json
  kol         <folder>/A/batch_<k>/posts.json, criteria.md, labels.json (written by the coder), and the same under B/
  attribution <folder>/A/cases.json, rule.md, readings.json (written by the reader), and the same under B/
"""
import json
import random
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.coding import copies_passage, without_mailboxes  # noqa: E402
from snprice.files import atomic_write  # noqa: E402
from snprice.io import attribution_readings, polarity_labels, read_json, read_table  # noqa: E402
from snprice.kol import ATTRIBUTIONS, LABELS, by_number_alone  # noqa: E402

BATCH_SIZE = 22                  # subnets per batch of website facts
KOL_BATCH_POSTS = 150            # posts per batch of labels
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


def web_prepare(folder, wave, only=()):
    protocol = (paths.CONFIG / "coding_protocol.md").read_text(encoding="utf-8")
    (folder / "dossiers").mkdir(parents=True, exist_ok=True)
    (folder / "out").mkdir(exist_ok=True)
    atomic_write(folder / "protocol.md", sections(protocol, WEB_SECTIONS))
    shutil.copy(paths.CONFIG / "category_codebook.md", folder / "categories.md")
    netuids = sorted(int(r["netuid"]) for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv"))
    if only:
        unknown = sorted(set(only) - set(netuids))
        if unknown:
            raise SystemExit(f"no such netuid in this wave: {unknown}")
        netuids = sorted(set(only))
    for n in netuids:
        shutil.copy(paths.raw_dir("dossiers") / f"{n}.txt", folder / "dossiers" / f"{n}.txt")
    order = netuids[:]
    random.Random(wave).shuffle(order)                 # the same batches on every run of a wave
    batches = [sorted(order[i:i + BATCH_SIZE]) for i in range(0, len(order), BATCH_SIZE)]
    dump(folder / "batches.json", batches)
    print(f"{len(netuids)} dossiers in {len(batches)} batches; both coders get the same batches (batches.json)")


def web_merge(folder, wave):
    """Collect the coders' answers. Answers for a subnet replace what the coder said about it before
    (a subnet is coded again when its site could be read only later)."""
    netuids = sorted(int(r["netuid"]) for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv"))
    asked = sorted(n for batch in json.loads((folder / "batches.json").read_text(encoding="utf-8")) for n in batch)
    for coder in "AB":
        rows = []
        for path in sorted((folder / "out").glob(f"coder_{coder}_batch_*.json")):
            rows += json.loads(path.read_text(encoding="utf-8"))
        got = sorted(int(r["netuid"]) for r in rows)
        if got != asked:
            raise SystemExit(f"coder {coder}: missing {sorted(set(asked) - set(got))}, twice or not asked "
                             f"{sorted(n for n in set(got) if got.count(n) > 1 or n not in asked)}")
        merged = {int(r["netuid"]): r for r in read_json(paths.MANUAL / f"web_coding_wave{wave}_coder_{coder}.json", default=[])}
        merged.update({int(r["netuid"]): r for r in rows})
        if sorted(merged) != netuids:
            raise SystemExit(f"coder {coder}: no answer for {sorted(set(netuids) - set(merged))}, "
                             f"answers for unknown netuids {sorted(set(merged) - set(netuids))}")
        dump(paths.MANUAL / f"web_coding_wave{wave}_coder_{coder}.json", [merged[n] for n in netuids])
        print(f"coder {coder}: {len(rows)} subnets coded, {len(merged)} in data/manual/web_coding_wave{wave}_coder_{coder}.json")


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
    batches = [todo[i:i + KOL_BATCH_POSTS] for i in range(0, len(todo), KOL_BATCH_POSTS)]
    for coder in "AB":
        for k, batch in enumerate(batches, 1):
            sub = folder / coder / f"batch_{k}"
            sub.mkdir(parents=True, exist_ok=True)
            dump(sub / "posts.json", batch)
            shutil.copy(paths.CONFIG / "polarity_criteria.md", sub / "criteria.md")
    print(f"{len(todo)} posts with {sum(len(t['subnets']) for t in todo)} pairs still to label, "
          f"in {len(batches)} batches per coder under {folder}")


def kol_merge(folder, wave):
    for coder in "AB":
        asked, new = set(), []
        for sub in sorted((folder / coder).glob("batch_*"), key=lambda d: int(d.name.split("_")[1])):
            posts = json.loads((sub / "posts.json").read_text(encoding="utf-8"))
            asked |= {(p["post_id"], s["netuid"]) for p in posts for s in p["subnets"]}
            if not (sub / "labels.json").exists():
                raise SystemExit(f"coder {coder}: {sub.name} has no labels.json yet")
            new += json.loads((sub / "labels.json").read_text(encoding="utf-8"))
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


def attribution_prepare(folder, wave):
    """Cases for the two readers of config/kol_attribution.md: posts that name a subnet by number alone."""
    posts = read_json(paths.raw_dir("kol") / "coding_input.json")
    if posts is None:
        raise SystemExit("run `python collect/14_kol.py posts` first")
    posts = {str(p["post_id"]): p for p in posts}
    cfg = paths.snapshot()        # read by both readers, in this wave or carried over from an earlier one
    done = set(attribution_readings(cfg, "A")) & set(attribution_readings(cfg, "B"))
    history = {int(h["netuid"]): h for h in read_table(paths.INTERMEDIATE / f"history_wave{wave}.csv")}
    roster = {int(r["netuid"]): r for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")}
    names = {}
    for row in read_table(paths.INTERMEDIATE / f"names_wave{wave}.csv"):
        names.setdefault(int(row["netuid"]), []).append({"set_on": (row["utc"] or "")[:10], "name": row["name"]})
    cases = []
    for m in read_table(paths.EVIDENCE / f"kol_mentions_wave{wave}.csv"):
        key = (str(m["post_id"]), int(m["netuid"]))
        if not by_number_alone(m["rules"]) or key in done:
            continue
        post, n = posts[key[0]], key[1]        # neither the account nor the coders' labels are shown
        cases.append({"post_id": key[0], "posted": m["created"][:10], "text": post["text"], "netuid": n,
                      "current_project": next(s["name"] for s in post["subnets"] if int(s["netuid"]) == n),
                      "current_project_since": history[n]["project_start_utc"][:10],
                      "registered": roster[n]["registered_utc"][:10],
                      "names_on_this_netuid": names.get(n, [])})
    cases.sort(key=lambda c: (c["netuid"], c["posted"], c["post_id"]))
    for reader in "AB":
        (folder / reader).mkdir(parents=True, exist_ok=True)
        dump(folder / reader / "cases.json", cases)
        shutil.copy(paths.CONFIG / "kol_attribution.md", folder / reader / "rule.md")
    print(f"{len(cases)} cases still to read, one copy per reader under {folder}")


def attribution_merge(folder, wave):
    texts = {str(p["post_id"]): p["text"] for p in read_json(paths.raw_dir("kol") / "coding_input.json")}
    for reader in "AB":
        sub = folder / reader
        asked = {(str(c["post_id"]), int(c["netuid"])) for c in json.loads((sub / "cases.json").read_text(encoding="utf-8"))}
        if not (sub / "readings.json").exists():
            raise SystemExit(f"reader {reader}: no readings.json yet")
        new = json.loads((sub / "readings.json").read_text(encoding="utf-8"))
        got = {}
        for r in new:
            key = (str(r["post_id"]), int(r["netuid"]))
            answer, reason = r["refers_to_current"], (r.get("reason") or "").strip()
            if answer not in ATTRIBUTIONS:
                raise SystemExit(f"reader {reader}: unknown answer {answer!r} for {key}")
            if answer == "no" and not reason:
                raise SystemExit(f"reader {reader}: {key} is answered no without a reason")
            if copies_passage(reason, texts.get(key[0], "")):
                raise SystemExit(f"reader {reader}: the reason for {key} repeats a passage of the post; it has to be reworded")
            got[key] = {"refers_to_current": answer, "reason": reason}
        if set(got) != asked or len(new) != len(asked):
            raise SystemExit(f"reader {reader}: {len(asked - set(got))} cases without an answer, "
                             f"{len(set(got) - asked)} answers for cases that were not asked, {len(new) - len(got)} given twice")
        earlier = read_json(paths.MANUAL / f"kol_attribution_wave{wave}_reader_{reader}.json", default=[])
        merged = {(str(r["post_id"]), int(r["netuid"])): {"refers_to_current": r["refers_to_current"], "reason": r["reason"]}
                  for r in earlier}
        merged.update(got)
        rows = [{"post_id": p, "netuid": n, **answer} for (p, n), answer in sorted(merged.items())]
        dump(paths.MANUAL / f"kol_attribution_wave{wave}_reader_{reader}.json", rows)
        print(f"reader {reader}: {len(got)} new answers ({sum(1 for a in got.values() if a['refers_to_current'] == 'no')} no), "
              f"{len(rows)} in data/manual/kol_attribution_wave{wave}_reader_{reader}.json")


STEPS = {("web", "prepare"): web_prepare, ("web", "merge"): web_merge,
         ("whitepaper", "prepare"): whitepaper_prepare, ("whitepaper", "merge"): whitepaper_merge,
         ("kol", "prepare"): kol_prepare, ("kol", "merge"): kol_merge,
         ("attribution", "prepare"): attribution_prepare, ("attribution", "merge"): attribution_merge}

if __name__ == "__main__":
    step = tuple(sys.argv[1:3])
    if len(sys.argv) < 4 or step not in STEPS or (len(sys.argv) > 4 and step != ("web", "prepare")):
        raise SystemExit(__doc__)
    target = Path(sys.argv[3]).resolve()
    if paths.ROOT in target.parents or target == paths.ROOT:
        raise SystemExit("the working folder must lie outside the repository: it holds texts that are not republished")
    if len(sys.argv) > 4:
        web_prepare(target, paths.snapshot()["wave"], only=[int(a) for a in sys.argv[4:]])
    else:
        STEPS[step](target, paths.snapshot()["wave"])
