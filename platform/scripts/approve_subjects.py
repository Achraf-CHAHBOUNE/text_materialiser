"""Decide which of the subjects a model suggested become part of the vocabulary.

`ingest` never adopts a subject the model invented. It writes it to a proposals file
and leaves that ruling without one, because a legal taxonomy is not something a model
gets to extend on its own. This is the other half of that: it turns the proposals into
a short list a person can rule on, and then applies the ruling.

    python approve_subjects.py review      # write the list to decide on
    ...edit it: set "approve" to true or false...
    python approve_subjects.py apply       # file the rulings under what you approved

Review collapses the list first, so what you read is as short as it can honestly be:

  - suggestions that are spellings of one another are merged, under the one suggested
    most often -- 'وجبات الكراء' and 'إصلاح الخطأ المادي' were each proposed several
    ways;
  - anything that turns out to be a subject the court already uses is filed
    immediately and never reaches the list, which is what reconcile_proposals does;
  - what is left is sorted by how many rulings turn on it, so the decisions that
    matter come first.

Nothing is adopted until `apply`, and `apply` only ever touches rulings that still
have no subject.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    _here = Path(__file__).resolve().parent
except NameError:
    _here = Path.cwd()
sys.path.insert(0, str(_here))
_backend = _here.parent / "backend"
if (_backend / "db.py").exists():
    sys.path.insert(0, str(_backend))
sys.stdout.reconfigure(encoding="utf-8")

import db  # noqa: E402
import headnotes  # noqa: E402
from reconcile_proposals import loose  # noqa: E402


def _paths() -> tuple:
    root = Path(os.getenv("DB_DIR", "data"))
    return root / "proposed_subjects.json", root / "subject_review.json"


def review() -> int:
    props_path, review_path = _paths()
    props = json.loads(props_path.read_text(encoding="utf-8")) if props_path.exists() else []
    if not props:
        print(f"no proposals in {props_path}")
        return 0

    groups: dict = defaultdict(lambda: {"spellings": Counter(), "chambers": Counter(),
                                        "doc_ids": []})
    for p in props:
        g = groups[loose(p["proposed"])]
        g["spellings"][p["proposed"]] += 1
        g["chambers"][p["chamber"]] += 1
        g["doc_ids"].append(p["doc_id"])

    # keep whatever an earlier review already decided, so editing is not thrown away
    previous = {}
    if review_path.exists():
        for item in json.loads(review_path.read_text(encoding="utf-8")):
            previous[item["key"]] = (item.get("approve"), item.get("label"))

    out = []
    for key, g in groups.items():
        label = g["spellings"].most_common(1)[0][0]
        was_approved, was_label = previous.get(key, (None, None))
        out.append({
            "key": key,
            "approve": was_approved,              # null until a person decides
            "label": was_label or label,          # edit this to rename it
            "rulings": len(g["doc_ids"]),
            "chambers": dict(g["chambers"].most_common()),
            "also_spelled": [s for s, _ in g["spellings"].most_common()[1:]],
        })
    out.sort(key=lambda x: -x["rulings"])
    review_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    undecided = sum(1 for x in out if x["approve"] is None)
    print(f"  proposals           : {len(props):,} rulings")
    print(f"  distinct suggestions: {len(groups):,} after merging spellings")
    print(f"  still to decide     : {undecided:,}")
    print(f"\n  written to {review_path}")
    print("  set \"approve\" to true or false on each, then: approve_subjects.py apply\n")
    print("  the ones that decide the most rulings:")
    for x in out[:15]:
        also = f"   (also: {', '.join(x['also_spelled'])})" if x["also_spelled"] else ""
        print(f"    {x['rulings']:>4}  {x['label']}{also}")
    return 0


def apply() -> int:
    props_path, review_path = _paths()
    if not review_path.exists():
        print(f"no {review_path}: run `approve_subjects.py review` first", file=sys.stderr)
        return 2
    decisions = json.loads(review_path.read_text(encoding="utf-8"))
    approved = {d["key"]: d["label"] for d in decisions if d.get("approve") is True}
    refused = {d["key"] for d in decisions if d.get("approve") is False}
    if not approved and not refused:
        print("nothing decided yet: every \"approve\" is still null")
        return 0

    props = json.loads(props_path.read_text(encoding="utf-8")) if props_path.exists() else []
    D = db.Decision
    filed, left = 0, []
    with db.session() as s:
        for p in props:
            key = loose(p["proposed"])
            if key in approved:
                d = s.get(D, p["doc_id"])
                if d is not None and not d.theme:        # never overwrite one it has
                    d.theme = approved[key]
                    d.theme_key = headnotes.normalise(approved[key])
                    d.theme_source = "model"
                    filed += 1
            elif key not in refused:
                left.append(p)                           # still undecided, keep waiting
        s.commit()
    props_path.write_text(json.dumps(left, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"  approved subjects : {len(approved):,}")
    print(f"  rulings filed     : {filed:,}")
    print(f"  refused subjects  : {len(refused):,}  (those rulings keep no subject)")
    print(f"  still undecided   : {len(left):,} rulings left in {props_path.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Rule on the subjects a model suggested")
    ap.add_argument("action", choices=["review", "apply"])
    args = ap.parse_args()
    db.init_db()
    return review() if args.action == "review" else apply()


if __name__ == "__main__":
    raise SystemExit(main())
