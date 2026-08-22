"""Streamlit UI for the Arabic PII anonymizer.

Run:  streamlit run app.py

Lets a user upload PDF/DOC/DOCX files, pick the output folder, run the pipeline,
preview the case index, and download the anonymized .docx files + CSVs.
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from anonymizer.config import Settings
from anonymizer.pipeline import Pipeline, RunOptions
from anonymizer.utils.logging import setup_logging

st.set_page_config(page_title="Arabic PII Anonymizer", page_icon="🛡️", layout="wide")
st.title("🛡️ Arabic Legal-Document PII Anonymizer")
st.caption("Upload court rulings → anonymize PII → classify → link cases → download.")

base = Settings.load()  # defaults from .env


def browse_folder() -> str:
    """Open a native folder picker (local desktop). Returns '' on cancel/failure."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory()
        root.destroy()
        return path or ""
    except Exception as exc:  # no display / tkinter missing → fall back to typing
        st.warning(f"Folder picker unavailable ({exc}); type the path instead.")
        return ""


def folder_input(label: str, key: str, default: str):
    """Text field + 📁 browse button that share one session-state value."""
    st.session_state.setdefault(key, default)
    c1, c2 = st.columns([5, 1])
    if c2.button("📁", key=f"browse_{key}", help="Browse…"):
        picked = browse_folder()
        if picked:
            st.session_state[key] = picked
    return c1.text_input(label, key=key)

# ----------------------------- sidebar: config -----------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    provider = st.selectbox("Provider", ["gemini"], index=0)
    api_key = st.text_input("Gemini API key", value=base.api_key, type="password")
    model = st.text_input("Model", value=base.model)
    output_dir = folder_input("Output folder", "out_dir", str(base.output_dir))
    db_path = st.text_input("Case DB file (separate folder)", value=str(base.db_path))
    workers = st.number_input("Parallel workers", 1, 16, value=base.max_workers)
    token = st.text_input("Replacement token", value=base.replacement_token)
    overwrite = st.checkbox("Reprocess existing (overwrite)", value=True)

# ----------------------------- main: input source --------------------------
source = st.radio("Input source", ["Upload files", "Folder on disk"], horizontal=True)

uploaded = None
folder_path = ""
ready = False
if source == "Upload files":
    uploaded = st.file_uploader(
        "Upload documents (PDF / DOC / DOCX)",
        type=["pdf", "doc", "docx"],
        accept_multiple_files=True,
    )
    ready = bool(uploaded)
else:
    folder_path = folder_input("Input folder (path on this machine)", "in_dir", str(base.input_dir))
    p = Path(folder_path) if folder_path else None
    if p and p.is_dir():
        n_found = sum(1 for f in p.rglob("*")
                      if f.is_file() and f.suffix.lower() in {".pdf", ".doc", ".docx"}
                      and not f.name.startswith("~$"))
        st.caption(f"📂 {n_found} document(s) found in this folder.")
        ready = n_found > 0
    elif folder_path:
        st.warning("Folder not found.")

run = st.button("🚀 Anonymize", type="primary", disabled=not ready)

if run:
    if not api_key:
        st.error("Please enter your Gemini API key in the sidebar.")
        st.stop()

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if source == "Upload files":
        in_dir = Path(tempfile.mkdtemp(prefix="anon_in_"))
        for uf in uploaded:
            (in_dir / uf.name).write_bytes(uf.getbuffer())
    else:
        in_dir = Path(folder_path)  # process files already on disk (no copy)

    settings = replace(
        base,
        provider=provider,
        api_key=api_key,
        model=model,
        input_dir=in_dir,
        output_dir=out_dir,
        state_file=out_dir / ".anonymizer_state.json",
        db_path=Path(db_path),
        max_workers=int(workers),
        replacement_token=token,
    )
    setup_logging(settings.log_level)

    # Live progress bar + per-document status feed.
    progress = st.progress(0.0, text="Starting…")
    status = st.empty()
    feed_area = st.empty()
    feed_rows: list[dict] = []
    running = {"cost": 0.0}

    def on_progress(ev: dict):
        frac = ev["done"] / max(ev["total"], 1)
        progress.progress(frac, text=f"{ev['done']}/{ev['total']} documents")
        if ev["ok"]:
            running["cost"] += ev.get("cost", 0.0)
            status.info(f"✅ {ev['doc_id']} — {ev.get('level','?')} · "
                        f"{ev.get('category','')} · {ev.get('pii',0)} PII · "
                        f"running cost ${running['cost']:.4f}")
            feed_rows.append({"file": ev["doc_id"], "level": ev.get("level", "?"),
                              "category": ev.get("category", ""), "PII": ev.get("pii", 0),
                              "status": "ok"})
        else:
            status.error(f"❌ {ev['doc_id']} — {ev.get('error','failed')}")
            feed_rows.append({"file": ev["doc_id"], "level": "-", "category": "-",
                              "PII": 0, "status": "FAILED"})
        feed_area.dataframe(feed_rows, use_container_width=True, hide_index=True)

    try:
        pipeline = Pipeline(settings)
        totals = pipeline.run(RunOptions(overwrite=overwrite), progress_cb=on_progress)
    except Exception as exc:
        st.error(f"Run failed: {exc}")
        st.stop()

    progress.progress(1.0, text="Complete")
    st.success("Done!")
    c = st.columns(4)
    c[0].metric("Documents", totals["documents"])
    c[1].metric("Pages", totals["pages"])
    c[2].metric("PII redacted", totals["pii"])
    c[3].metric("Est. cost", f"${totals['cost']:.4f}")
    if totals["failed"]:
        st.warning(f"{totals['failed']} document(s) failed — rerun to retry.")

    st.session_state["last_out_dir"] = str(out_dir)

# ----------------------------- results / downloads --------------------------
out_dir = Path(st.session_state.get("last_out_dir", output_dir))
cases_csv = out_dir / "cases.csv"
index_csv = out_dir / "index.csv"

if cases_csv.exists() or index_csv.exists():
    st.divider()
    st.subheader("📁 Results")

    tab1, tab2 = st.tabs(["Cases (linked)", "Documents index"])
    if cases_csv.exists():
        df = pd.read_csv(cases_csv, encoding="utf-8-sig")
        tab1.dataframe(df, use_container_width=True)
        tab1.download_button("⬇️ Download cases.csv", cases_csv.read_bytes(),
                             file_name="cases.csv", mime="text/csv")
    if index_csv.exists():
        df = pd.read_csv(index_csv, encoding="utf-8-sig")
        tab2.dataframe(df, use_container_width=True)
        tab2.download_button("⬇️ Download index.csv", index_csv.read_bytes(),
                             file_name="index.csv", mime="text/csv")

    docx_files = sorted(out_dir.glob("*.docx"))
    if docx_files:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in docx_files:
                z.write(f, arcname=f.name)
        st.download_button(f"⬇️ Download {len(docx_files)} anonymized .docx (zip)",
                           buf.getvalue(), file_name="anonymized_docx.zip",
                           mime="application/zip")
