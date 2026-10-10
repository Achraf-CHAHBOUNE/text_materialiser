"""Match the subjects the model proposed against the ones we already have.

The classifier only accepted a subject that appeared in the list sent to it: that
chamber's own vocabulary, compared on the ordinary key. Both of those were too strict,
and the proposals show it:

  - the key keeps a definite article that is not on the first word, so
    "دعوى الإفراغ" and "دعوى إفراغ" count as two different subjects, and so do
    "طعن بالإلغاء" and "طعن بإلغاء";
  - the list was per chamber, so a subject the court uses in one chamber was unknown
    in another. "حجز تحفظي" is commercial vocabulary, and a civil ruling that needed
    it had to propose it as new.

Neither is a new subject. This re-matches every proposal on a looser key against the
whole corpus vocabulary and files the ones that were ours all along, under the
spelling the court uses most. Whatever is left is genuinely new and still waits for a
person.

Nothing is sent anywhere and no new text is written: this only decides which existing
subject a ruling belongs under.

    python reconcile_proposals.py --dry-run
    python reconcile_proposals.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

try:
    _backend = Path(__file__).resolve().parents[1] / "backend"
except NameError:
    _backend = Path.cwd()
if not (_backend / "db.py").exists():
    _backend = Path.cwd()
sys.path.insert(0, str(_backend))
sys.stdout.reconfigure(encoding="utf-8")

import db  # noqa: E402
import headnotes  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


def loose(term: str) -> str:
    """A key that ignores the definite article wherever it sits, and alef forms.

    Only for deciding that two spellings mean the same subject. The canonical key
    stays headnotes.normalise, so nothing already stored has to change.
    """
    t = headnotes.MARKS.sub("", term)
    t = re.sub(r"[أإآٱ]", "ا", t)
    # The article on any word, not only the first. Stripping it from behind an
    # attached letter as well (بالإلغاء -> بإلغاء) is tempting and wrong: once alef
    # forms are unified, بإلغاء is no longer distinguishable from ب + ال + غاء, so the
    # rule fires twice on one spelling and once on the other and pushes them further
    # apart. Those few stay proposals, which is the safe place for a judgement call.
    t = re.sub(r"\bال(?=[^\s]{3})", "", t)
    return re.sub(r"\s+", " ", t).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Fold proposals back into the vocabulary")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    D = db.Decision
    db.init_db()

    # the whole approved vocabulary, every chamber, commonest spelling wins
    with db.session() as s:
        rows = s.execute(
            select(D.theme, func.count(D.doc_id))
            .where(D.theme_source == "court").group_by(D.theme)).all()
    best: dict = {}
    for label, n in rows:
        k = loose(label)
        if n > best.get(k, (0, ""))[0]:
            best[k] = (n, label)
    known = {k: v[1] for k, v in best.items()}
    print(f"vocabulary: {len(known):,} subjects the court uses")

    f = Path(os.getenv("DB_DIR", "data")) / "proposed_subjects.json"
    props = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    print(f"proposals : {len(props):,} rulings")

    matched, left = [], []
    for p in props:
        hit = known.get(loose(p["proposed"]))
        (matched if hit else left).append((p, hit))

    print(f"\n  were ours all along : {len(matched):,}")
    print(f"  genuinely new       : {len(left):,}")

    shown = Counter((p["proposed"], hit) for p, hit in matched)
    print("\n  folded in, most common first:")
    for (was, now), n in shown.most_common(12):
        print(f"     {n:>4}  {was}   ->   {now}")

    if not args.dry_run and matched:
        with db.session() as s:
            for p, hit in matched:
                d = s.get(D, p["doc_id"])
                if d is None or d.theme:
                    continue
                d.theme = hit
                d.theme_key = headnotes.normalise(hit)
                d.theme_source = "model"
            s.commit()
        f.write_text(json.dumps([p for p, _ in left], ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"\n  filed {len(matched):,} rulings; {len(left):,} proposals left in {f.name}")

    still = Counter(p["proposed"] for p, _ in left)
    print(f"\n  still proposed: {len(still):,} distinct. The most asked for:")
    for name, n in still.most_common(15):
        print(f"     {n:>4}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
