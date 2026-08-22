"""Case-linkage tests: chaining works regardless of arrival order (offline, no LLM)."""
from anonymizer.core.casedb import CaseDB
from anonymizer.core.identifiers import Ident


def _ingest_all(db, order):
    docs = {
        "ibtidai": dict(
            doc_id="ibtidai_12345", source="i", level="ابتدائي",
            own=Ident("المحكمة التجارية", "الدار البيضاء", "12345", "15/10/2015", "8888/1/2014"),
            category="الغرفة التجارية", outcome="", refs=[],
        ),
        "istinaf": dict(
            doc_id="istinaf_1990", source="a", level="استئناف",
            own=Ident("محكمة الاستئناف التجارية", "الدار البيضاء", "1990", "08/03/2016", "4443/8202/2015"),
            category="الغرفة الاستئنافية", outcome="تعديل",
            refs=[Ident("المحكمة التجارية", "الدار البيضاء", "12345", "15/10/2015", "8888/1/2014")],
        ),
        "naqd": dict(
            doc_id="naqd_589-3", source="n", level="نقض",
            own=Ident("محكمة النقض", "الرباط", "589-3", "26-11-2019", "1537-3-3-2016"),
            category="غير محدد", outcome="نقض وإحالة",
            # cites the appeal with DASH separators (real formatting variance)
            refs=[Ident("محكمة الاستئناف التجارية", "الدار البيضاء", "1990", "08-03-2016", "4443-8202-2015")],
        ),
    }
    for key in order:
        db.ingest(**docs[key])
        db.relink()  # relink after each ingest (simulates separate runs)


def _case_ids(db):
    return [r["case_id"] for r in db.con.execute("SELECT case_id FROM documents")]


def test_forward_order(tmp_path):
    db = CaseDB(tmp_path / "c.db")
    _ingest_all(db, ["ibtidai", "istinaf", "naqd"])
    ids = _case_ids(db)
    assert len(set(ids)) == 1 and all(ids)  # all three in ONE case


def test_reverse_order(tmp_path):
    # cassation first, then appeal, then first-instance ("months later")
    db = CaseDB(tmp_path / "c.db")
    _ingest_all(db, ["naqd", "istinaf", "ibtidai"])
    ids = _case_ids(db)
    assert len(set(ids)) == 1 and all(ids)


def test_appeal_first_then_firstinstance(tmp_path):
    db = CaseDB(tmp_path / "c.db")
    _ingest_all(db, ["istinaf", "ibtidai"])
    ids = _case_ids(db)
    assert len(set(ids)) == 1  # appeal + first-instance linked even though appeal came first


def test_scattered_order(tmp_path):
    db = CaseDB(tmp_path / "c.db")
    _ingest_all(db, ["istinaf", "naqd", "ibtidai"])
    ids = _case_ids(db)
    assert len(set(ids)) == 1
