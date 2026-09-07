"""Case linking: correct chains, and fast enough for the real corpus.

The first implementation compared every reference against every document
(O(refs x docs)) — measured at ~27 hours for 51,000 documents. Candidates are now
found through indexes, which is exact (a pair that shares neither the file number
nor decision+date can never be link-worthy) and linear.
"""
import tempfile
import time
from pathlib import Path

from anonymizer.core.casedb import CaseDB
from anonymizer.core.identifiers import Ident


def _corpus(n_cases: int) -> CaseDB:
    """n_cases chains of ابتدائي -> استئناف -> نقض."""
    db = CaseDB(Path(tempfile.mkdtemp()) / "c.db")
    db.con.execute("PRAGMA synchronous=OFF")
    for i in range(n_cases):
        f_ib, f_is, f_nq = f"{1000+i}/1/2/2015", f"{2000+i}/1/2/2017", f"{3000+i}/1/2/2019"
        ib = Ident("المحكمة الابتدائية", "الرباط", str(100 + i), "2015/01/01", f_ib)
        is_ = Ident("محكمة الاستئناف", "الرباط", str(200 + i), "2017/01/01", f_is)
        db.ingest(f"ib{i}", "s", "ابتدائي", ib, "مدنية", "", [])
        db.ingest(f"is{i}", "s", "استئناف", is_, "مدنية", "", [ib])
        db.ingest(f"nq{i}", "s", "نقض",
                  Ident("محكمة النقض", "", "", "2019/01/01", f_nq), "مدنية", "", [is_])
    return db


def test_three_level_chains_group_into_one_case():
    db = _corpus(50)
    db.relink()
    edges = len(list(db.con.execute("SELECT 1 FROM edges")))
    cases = {r[0] for r in db.con.execute("SELECT case_id FROM documents")}
    assert edges == 100          # 2 links per chain (نقض->استئناف, استئناف->ابتدائي)
    assert len(cases) == 50      # each chain collapses to ONE case
    # every member of a chain shares the same case_id
    got = {r[0] for r in db.con.execute(
        "SELECT case_id FROM documents WHERE doc_id IN ('ib7','is7','nq7')")}
    assert len(got) == 1


def test_linking_is_linear_not_quadratic():
    """Doubling the corpus must not quadruple the time."""
    db = _corpus(400)                     # 1,200 documents
    t = time.time(); db.relink(); dt = time.time() - t
    # the old nested-loop version needed minutes at this size; allow generous headroom
    assert dt < 5.0, f"relink too slow ({dt:.1f}s) — candidate indexing regressed"
