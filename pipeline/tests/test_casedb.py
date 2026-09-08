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


# --- normalization regressions -------------------------------------------------
def test_two_digit_year_in_file_number_links_to_the_four_digit_spelling():
    """95/1622/16 and 95/1622/2016 are the same file; before, they never linked."""
    from anonymizer.core.identifiers import Ident, canon_file_no, match_score

    assert canon_file_no("95/1622/16") == canon_file_no("95/1622/2016")
    ref = Ident("محكمة الاستئناف بالرباط", "الرباط", "512", "12/03/2016", "95/1622/16")
    own = Ident("محكمة الاستئناف بالرباط", "الرباط", "512", "12/03/2016", "95/1622/2016")
    _, conf = match_score(ref, own)
    assert conf == "high"


def test_a_trailing_two_digit_part_that_is_not_a_year_is_left_alone():
    """Expanding a chamber/section number would invent links between unrelated files."""
    from anonymizer.core.identifiers import canon_file_no

    assert canon_file_no("1622/16") == "1622/16"          # too few parts to guess
    assert canon_file_no("16/1622/2016") == "16/1622/2016"  # year already present


def test_a_reference_to_several_joined_files_yields_one_ref_each():
    """"الملفين عدد X و Y" reviews two lower rulings — both must be captured."""
    from anonymizer.core.identifiers import local_extract

    text = ("وبعد المداولة صدر القرار عدد 512 في الملفين عدد 1622/95 و 1623/95 "
            "بتاريخ 12/03/2016 عن محكمة الاستئناف بالرباط في القضية")
    _, _, refs = local_extract(text)
    assert [r.file_no for r in refs] == ["1622/95", "1623/95"]


def test_relink_matches_rows_normalized_by_an_older_ruleset(tmp_path):
    """relink must key off recomputed idents, not the stored file_norm column."""
    from anonymizer.core.casedb import CaseDB
    from anonymizer.core.identifiers import Ident

    db = CaseDB(tmp_path / "c.db")
    low = Ident("محكمة الاستئناف بالرباط", "الرباط", "512", "12/03/2016", "95/1622/2016")
    db.ingest("low", "low.pdf", "استئناف", low, "", "", [])
    # Simulate a row written before the year rule existed.
    db.con.execute("UPDATE documents SET file_norm='95/1622/16' WHERE doc_id='low'")
    db.con.commit()

    high = Ident("محكمة النقض", "", "9", "01/01/2018", "1/1/2018")
    db.ingest("high", "high.pdf", "نقض", high, "", "",
              [Ident("محكمة الاستئناف بالرباط", "الرباط", "512", "12/03/2016", "95/1622/16")])
    db.relink()

    edges = list(db.con.execute("SELECT parent_doc, child_doc FROM edges"))
    assert [(e["parent_doc"], e["child_doc"]) for e in edges] == [("high", "low")]
    assert db.document("low")["case_id"] == db.document("high")["case_id"]
    db.close()


def test_a_joined_file_number_from_the_model_is_split_into_each_file():
    """The model names several reviewed files in one field.

    Kept whole, canon_file_no runs the digits together into a key that matches
    nothing, so the lower rulings are never linked.
    """
    from anonymizer.core.identifiers import canon_file_no, split_file_numbers

    joined = "444 /1606 /2016 وعدد445 /1606/2016"
    assert canon_file_no(joined) == "444/1606/2016/445/1606/2016"   # the useless key
    assert [canon_file_no(f) for f in split_file_numbers(joined)] == [
        "444/1606/2016", "445/1606/2016"]


def test_splitting_leaves_an_ordinary_single_file_number_alone():
    from anonymizer.core.identifiers import split_file_numbers

    assert split_file_numbers("1622/95") == ["1622/95"]
    assert split_file_numbers("") == [""]
