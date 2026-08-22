"""SQLite-backed incremental case linker.

Stores every processed document with its own identity + the lower decisions it
references, then links them into cases by matching references to own-identities
(both directions, any arrival order) and grouping via connected components.

Tables:
  documents(doc_id, source, level, court, city, decision_no, date,
            file_no, file_norm, date_norm, category, outcome, case_id, review)
  doc_refs(doc_id, ref_ix, court, city, decision_no, date, file_no, file_norm, date_norm)
  edges(parent_doc, child_doc, confidence, score)   # parent = higher court

CSV export is a simple read over these (design finalised later).
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Dict, List

from .identifiers import Ident, canon_date, canon_file_no, court_to_level, match_score

LEVEL_RANK = {"ابتدائي": 1, "استئناف": 2, "نقض": 3}
LEVEL_ORDER = ["ابتدائي", "استئناف", "نقض"]


class CaseDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self._create()

    def _create(self) -> None:
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents(
              doc_id TEXT PRIMARY KEY, source TEXT, level TEXT, court TEXT, city TEXT,
              decision_no TEXT, date TEXT, file_no TEXT, file_norm TEXT, date_norm TEXT,
              category TEXT, outcome TEXT, case_id TEXT, review TEXT, pii_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS doc_refs(
              doc_id TEXT, ref_ix INTEGER, court TEXT, city TEXT, decision_no TEXT,
              date TEXT, file_no TEXT, file_norm TEXT, date_norm TEXT
            );
            CREATE TABLE IF NOT EXISTS edges(
              parent_doc TEXT, child_doc TEXT, confidence TEXT, score INTEGER
            );
            CREATE INDEX IF NOT EXISTS ix_doc_filenorm ON documents(file_norm);
            CREATE INDEX IF NOT EXISTS ix_ref_filenorm ON doc_refs(file_norm);
            """
        )
        # Forward-migrate a DB created by an older schema (add columns that post-date it).
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(documents)")}
        if "pii_count" not in cols:
            self.con.execute("ALTER TABLE documents ADD COLUMN pii_count INTEGER DEFAULT 0")
        self.con.commit()

    # --- ingest ---------------------------------------------------------------
    def ingest(self, doc_id: str, source: str, level: str, own: Ident,
               category: str, outcome: str, refs: List[Ident], pii_count: int = 0) -> None:
        """Insert/replace one document and its downward references (dedup by doc_id)."""
        self.con.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
        self.con.execute("DELETE FROM doc_refs WHERE doc_id=?", (doc_id,))
        self.con.execute(
            """INSERT INTO documents(doc_id,source,level,court,city,decision_no,date,
               file_no,file_norm,date_norm,category,outcome,case_id,review,pii_count)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc_id, source, level, own.court, own.city, own.decision_no, own.date,
             own.file_no, own.file_norm, own.date_norm, category, outcome, "", "", pii_count),
        )
        for i, r in enumerate(refs):
            self.con.execute(
                """INSERT INTO doc_refs(doc_id,ref_ix,court,city,decision_no,date,
                   file_no,file_norm,date_norm) VALUES(?,?,?,?,?,?,?,?,?)""",
                (doc_id, i, r.court, r.city, r.decision_no, r.date,
                 r.file_no, r.file_norm, r.date_norm),
            )
        self.con.commit()

    # --- linking --------------------------------------------------------------
    def _docs(self) -> List[sqlite3.Row]:
        return list(self.con.execute("SELECT * FROM documents"))

    def relink(self) -> None:
        """Rebuild edges from refs↔own-ids, then assign case_id via components."""
        self.con.execute("DELETE FROM edges")
        docs = self._docs()
        # index own-identities
        own = {
            d["doc_id"]: Ident(d["court"], d["city"], d["decision_no"], d["date"], d["file_no"])
            for d in docs
        }
        levels = {d["doc_id"]: (d["level"] or "") for d in docs}

        for row in self.con.execute("SELECT * FROM doc_refs"):
            parent = row["doc_id"]
            ref = Ident(row["court"], row["city"], row["decision_no"], row["date"], row["file_no"])
            best = None  # (score, conf, child_doc)
            for child, oid in own.items():
                if child == parent:
                    continue
                # a parent (higher court) reviews a lower one: enforce rank if known
                pr, cr = LEVEL_RANK.get(levels[parent], 0), LEVEL_RANK.get(levels[child], 0)
                if pr and cr and pr <= cr:
                    continue
                score, conf = match_score(ref, oid)
                if conf not in ("high", "medium"):  # never auto-link on weak matches
                    continue
                if best is None or score > best[0]:
                    best = (score, conf, child)
            if best:
                self.con.execute(
                    "INSERT INTO edges(parent_doc,child_doc,confidence,score) VALUES(?,?,?,?)",
                    (parent, best[2], best[1], best[0]),
                )
        self.con.commit()
        self._assign_cases()

    def _assign_cases(self) -> None:
        docs = [d["doc_id"] for d in self._docs()]
        parent: Dict[str, str] = {d: d for d in docs}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for e in self.con.execute("SELECT parent_doc,child_doc FROM edges"):
            if e["parent_doc"] in parent and e["child_doc"] in parent:
                union(e["parent_doc"], e["child_doc"])

        # name each component by its lowest-level member's file/doc id
        comp: Dict[str, List[str]] = {}
        for d in docs:
            comp.setdefault(find(d), []).append(d)
        rows = {d["doc_id"]: d for d in self._docs()}
        for members in comp.values():
            rep = sorted(members, key=lambda d: (LEVEL_RANK.get(rows[d]["level"] or "", 9), d))[0]
            key = rows[rep]["file_norm"] or rep
            case_id = f"C:{key}"
            # review flag: worst confidence among the case's edges
            confs = [e["confidence"] for e in self.con.execute(
                "SELECT confidence FROM edges WHERE parent_doc IN (%s) OR child_doc IN (%s)"
                % (",".join("?" * len(members)), ",".join("?" * len(members))),
                members + members,
            )]
            review = "check" if any(c in ("low", "medium") for c in confs) else "ok"
            for d in members:
                self.con.execute("UPDATE documents SET case_id=?, review=? WHERE doc_id=?",
                                 (case_id, review, d))
        self.con.commit()

    # --- export ---------------------------------------------------------------
    def export_cases_csv(self, path: Path) -> int:
        docs = self._docs()
        by_case: Dict[str, List[sqlite3.Row]] = {}
        for d in docs:
            by_case.setdefault(d["case_id"] or f"C:{d['doc_id']}", []).append(d)

        # collect dangling references (referenced level not present) per case
        present_files = {d["file_norm"] for d in docs if d["file_norm"]}

        path.parent.mkdir(parents=True, exist_ok=True)
        cols = ["case_id", "category", "levels_present", "courts_passed",
                "ibtidai_file", "istinaf_file", "naqd_file",
                "appealed", "cassated", "missing_levels", "docs", "review"]
        n = 0
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for case_id, members in sorted(by_case.items()):
                by_lvl = {m["level"]: m for m in members}
                present = [lv for lv in LEVEL_ORDER if lv in by_lvl]
                present_set = set(present)
                courts = " → ".join(by_lvl[lv]["court"] or lv for lv in present)
                cat = next((m["category"] for m in members if m["category"]), "")
                review = next((m["review"] for m in members if m["review"]), "")

                # Levels we KNOW exist = present + referenced + implied by hierarchy
                member_ids = [m["doc_id"] for m in members]
                ref_courts = [r["court"] for r in self.con.execute(
                    "SELECT court FROM doc_refs WHERE doc_id IN (%s)"
                    % ",".join("?" * len(member_ids)), member_ids)]
                known = set(present_set)
                known |= {court_to_level(c) for c in ref_courts if court_to_level(c)}
                if "نقض" in present_set:       # cassation implies prior appeal + first instance
                    known |= {"ابتدائي", "استئناف"}
                if "استئناف" in present_set:    # appeal implies first instance
                    known |= {"ابتدائي"}
                missing = [lv for lv in LEVEL_ORDER if lv in known and lv not in present_set]

                def fno(lvl):
                    return by_lvl[lvl]["file_no"] if lvl in by_lvl else ""
                w.writerow([
                    case_id, cat, "، ".join(present), courts,
                    fno("ابتدائي"), fno("استئناف"), fno("نقض"),
                    "نعم" if "استئناف" in known else "لا",
                    "نعم" if "نقض" in known else "لا",
                    "، ".join(missing),
                    "؛ ".join(sorted(m["doc_id"] for m in members)),
                    review,
                ])
                n += 1
        return n

    def export_documents_csv(self, path: Path) -> int:
        """Per-document rows with the fields the frontend needs (level, case_id, review)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = list(self.con.execute("SELECT * FROM documents ORDER BY doc_id"))
        cols = ["file", "level", "category", "court", "pii_count", "case_id", "review"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for d in rows:
                w.writerow([d["doc_id"], d["level"] or "", d["category"] or "",
                            d["court"] or "", d["pii_count"] or 0,
                            d["case_id"] or "", d["review"] or ""])
        return len(rows)

    def document(self, doc_id: str) -> dict:
        """One document row (level, case_id, review, ids) as a plain dict, or {}."""
        row = self.con.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        return dict(row) if row else {}

    def links_for(self, doc_id: str) -> List[dict]:
        """Edges touching this document, from its own perspective (role + confidence)."""
        rows = self.con.execute(
            "SELECT parent_doc, child_doc, confidence FROM edges WHERE parent_doc=? OR child_doc=?",
            (doc_id, doc_id),
        )
        out: List[dict] = []
        for e in rows:
            if e["parent_doc"] == doc_id:      # this doc is the higher court
                out.append({"to": e["child_doc"], "role": "reviews", "confidence": e["confidence"]})
            else:                                # this doc was reviewed by a higher court
                out.append({"to": e["parent_doc"], "role": "reviewed_by", "confidence": e["confidence"]})
        return out

    def close(self) -> None:
        self.con.close()
