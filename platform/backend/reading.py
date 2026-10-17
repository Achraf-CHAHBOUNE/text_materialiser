"""The reader's side: browsing and searching the published rulings, reading one, its
French translation, reporting a problem, and downloading the Word file."""
from __future__ import annotations

import io
import mimetypes
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db
import versions
import library
import storage
import translate
from deps import current_user, flex_user

router = APIRouter()


# ---------------- client space (published only) ----------------
@router.get("/api/categories")
def categories(_: dict = Depends(current_user)) -> list:
    return db.CATEGORIES


# One page is at most PAGE_MAX rulings: asking for the whole corpus at once would let any
# signed-in reader tie up the server, and nobody reads 29,000 rows on a screen.
PAGE_MAX = 200


@router.get("/api/decisions")
def client_decisions(category: str = "", level: str = "",
                     limit: int = Query(50, ge=1, le=PAGE_MAX), offset: int = Query(0, ge=0),
                     _: dict = Depends(current_user)) -> list:
    return db.list_decisions(states=("published",), category=category, level=level,
                             limit=limit, offset=offset)


@router.get("/api/search")
def client_search(q: str = Query(""), category: str = "", level: str = "",
                  limit: int = Query(50, ge=1, le=PAGE_MAX), offset: int = Query(0, ge=0),
                  user: dict = Depends(current_user)) -> list:
    if offset == 0:                          # a search, not each page of it
        db.log_activity(user["email"], "search", q[:80])
    return db.search_decisions(q, states=("published",), category=category, level=level,
                               limit=limit, offset=offset)


# ---------------- client: browse (court > chamber > year > ruling) ----------------
@router.get("/api/browse/courts")
def browse_courts(_: dict = Depends(current_user)) -> list:
    """Every court with its chambers and their counts -- the menu page."""
    return db.browse_tree()


@router.get("/api/browse/years")
def browse_years(chamber: str = "", _: dict = Depends(current_user)) -> list:
    return db.browse_years(chamber)


@router.get("/api/browse/cities")
def browse_cities(chamber: str = "", _: dict = Depends(current_user)) -> list:
    return db.browse_cities(chamber)


@router.get("/api/browse/themes")
def browse_themes(chamber: str = "", lang: str = "ar", _: dict = Depends(current_user)) -> list:
    """The subjects rulings are filed under, with counts.

    These are the court's own words, taken from the headnote each ruling prints. The
    Cassation portal publishes no list of subjects to classify against -- its search
    offers a free-text box over the same line -- so there is no official vocabulary
    this could be checked against, and roughly half the corpus prints no subject.
    """
    return db.browse_themes(chamber, lang=_lang(lang))


@router.get("/api/browse/rulings")
def browse_rulings(chamber: str = "", year: str = "", city: str = "", theme: str = "",
                   q: str = Query(""), limit: int = 50, offset: int = 0, lang: str = "ar",
                   user: dict = Depends(current_user)) -> dict:
    """One page of the listing: number, date, city, chamber, subject -- and the total."""
    out = db.browse_rulings(chamber=chamber, year=year, city=city, theme=theme, q=q,
                            limit=min(limit, 200), offset=offset, lang=_lang(lang))
    if q.strip() and offset == 0:
        # a search that found nothing is what the corpus is missing: kept apart, to read
        db.log_activity(user["email"], "search" if out["total"] else "search_empty", q[:80])
    return out


LANGS = ("ar", "fr")


def _lang(lang: str) -> str:
    return lang if lang in LANGS else "ar"


@router.get("/api/decisions/{doc_id}")
def client_decision(doc_id: str, lang: str = "ar", user: dict = Depends(current_user)) -> dict:
    d = db.get_decision(doc_id, body=True)
    if not d or d["state"] != "published":            # not guessable into unpublished data
        raise HTTPException(status_code=404, detail="Not found")
    # only expose links whose target is also published
    d["links"] = [l for l in db.links_for(doc_id)
                  if (db.get_decision(l["to"]) or {}).get("state") == "published"]
    library.note_view(user)
    db.log_activity(user["email"], "view", doc_id)
    lang = _lang(lang)
    if lang != "ar":
        db.with_language(d, lang, db.i18n_for([doc_id], lang).get(doc_id),
                         db.subject_labels([d.get("theme_key", "")], lang))
    return d


# ---------------- reading a ruling in French ----------------
# The one place this platform talks to an AI service, and it sends only text a
# signed-in reader already has on screen: anonymized, gate-checked, never a file.
# A ruling is translated once and then served from the database (see translate.py).
@router.get("/api/decisions/{doc_id}/translation")
def client_translation(doc_id: str, lang: str = "fr", user: dict = Depends(current_user)) -> dict:
    """The stored translation, or {"ready": false} if nobody has asked for one yet."""
    d = db.get_decision(doc_id)
    if not d or d["state"] != "published":
        raise HTTPException(status_code=404, detail="Not found")
    # the headnote in French travels with the text: the page shows both or neither
    head = db.with_language({"theme_key": d.get("theme_key", "")}, _lang(lang),
                            db.i18n_for([doc_id], _lang(lang)).get(doc_id),
                            db.subject_labels([d.get("theme_key", "")], _lang(lang)))
    head.pop("theme_key", None)
    got = db.get_translation(doc_id, lang)
    if not got or got["stale"]:
        return {"ready": False, "lang": lang, "stale": bool(got and got["stale"]), **head}
    return {"ready": True, **got, **head}


@router.post("/api/decisions/{doc_id}/translation")
def client_translate(doc_id: str, lang: str = "fr", user: dict = Depends(current_user)) -> dict:
    """Translate now (or hand back the stored one). Costs a fraction of a cent, once."""
    if lang != "fr":
        raise HTTPException(status_code=400, detail="Only French is available")
    d = db.get_decision(doc_id, body=True)
    if not d or d["state"] != "published":
        raise HTTPException(status_code=404, detail="Not found")
    got = db.get_translation(doc_id, lang)
    if got and not got["stale"]:
        return {"ready": True, **got}
    # Two readers asking at once: the second waits for the first and gets its result,
    # so a ruling is paid for once whichever copy of the API each one reached.
    with db.exclusive(f"translate:{doc_id}:{lang}", wait=True):
        got = db.get_translation(doc_id, lang)
        if got and not got["stale"]:
            return {"ready": True, **got}
        try:
            text = translate.translate(d.get("body_text") or "")
        except translate.TranslationError as e:
            raise HTTPException(status_code=503, detail=str(e))
        model = os.getenv("TRANSLATE_MODEL", "gemini-2.5-flash-lite")
        db.save_translation(doc_id, lang, text, model, d.get("version", 0))
    db.log_activity(user["email"], "translate", doc_id)
    return {"ready": True, **(db.get_translation(doc_id, lang) or {})}


class ReportBody(BaseModel):
    quote: str = ""
    note: str = ""


@router.post("/api/decisions/{doc_id}/reports")
def client_report(doc_id: str, body: ReportBody, user: dict = Depends(current_user)) -> dict:
    """A reader flags a problem -- typically a name left visible -- for an admin."""
    d = db.get_decision(doc_id)
    if not d or d["state"] != "published":
        raise HTTPException(status_code=404, detail="Not found")
    if not (body.quote.strip() or body.note.strip()):
        raise HTTPException(status_code=400, detail="Select the text or describe the problem")
    rid = versions.add_report(doc_id, user["email"], body.quote.strip(), body.note.strip())
    if rid is None:
        raise HTTPException(status_code=429, detail="Too many open reports; wait for them to be handled")
    return {"id": rid}


@router.get("/api/decisions/{doc_id}/file")
def client_file(doc_id: str, request: Request, authorization: Optional[str] = Header(None),
                token: str = "") -> StreamingResponse:
    user = flex_user(request, authorization, token)
    d = db.get_decision(doc_id)
    if not d or d["state"] != "published":            # clients get published files only
        raise HTTPException(status_code=404, detail="Not found")
    if not d["file_name"] or not storage.STORE.exists(d["file_name"]):
        raise HTTPException(status_code=404, detail="File not found")
    ref = library.start_download(user, doc_id)
    db.log_activity(user["email"], "download", doc_id)
    data = storage.STORE.get(d["file_name"])
    if d["file_name"].lower().endswith(".docx"):
        when = time.strftime("%d/%m/%Y %H:%M")
        data = library.mark_docx(data, f"{user['email']} · {when} · réf. {ref}")
    media = mimetypes.guess_type(d["file_name"])[0] or "application/octet-stream"
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="{d["file_name"]}"'})
