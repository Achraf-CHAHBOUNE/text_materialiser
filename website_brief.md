**Web platform for consulting anonymized Moroccan court decisions**

---

## Flow

```
        ┌────────────────────────┐
        │   PIPELINE OUTPUT      │   JSON / XLSX  +  safe file
        └───────────┬────────────┘
                    ▼
        ┌────────────────────────┐
        │      IMPORT GATE       │   reject if personal data found
        └───────────┬────────────┘
                    ▼
        ┌────────────────────────┐
        │  ADMIN · INTEGRATION   │   review · correct · publish
        └───────────┬────────────┘
                    ▼
        ┌────────────────────────┐
        │       CATALOGUE        │   validated records only
        └───────────┬────────────┘
                    ▼
 ┌──────────────┐   │
 │   ADMIN ·    │──►│
 │   CLIENTS    │   ▼
 │ accounts,    │  ┌────────────────────────┐
 │ access       │  │     CLIENT SPACE       │  browse · search · view
 └──────────────┘  └────────────────────────┘
```

## 1. Admin — Integration

**Purpose:** load pipeline output, verify it, correct it, publish it.

| #   | Requirement                                                                                                                                                                                                                          |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| I-1 | Import a batch: JSON or XLSX records**plus** their anonymized files. Import must be resumable and must report what succeeded, what failed, and why.                                                                            |
| I-2 | **Import gate** — the platform must not trust that the files are clean. Refuse or quarantine anything that fails an automated check for personal data, and anything whose record doesn't match its file.                      |
| I-3 | Correct any extracted value:`رقم القرار`, `رقم الملف`, `تاريخ`, category, parties, the `استئناف ← نقض` link. Correcting must be fast — this is the most-used screen in the whole platform. |
| I-4 | Correct or replace the**file itself** — re-upload a properly anonymized version, or mask a name the pipeline missed, without leaving the platform.                                                                            |
| I-5 | **Every change is logged**: who, when, old value, new value. Never overwrite silently.                                                                                                                                         |
| I-6 | **Publication state** per record: `imported → under review → published → withdrawn`. Only `published` is visible to clients. Withdrawing must take effect immediately.                                                  |
| I-7 | A**work queue** showing what needs attention first: low-confidence extractions, conflicting fields, missing category, unresolved links, quarantined imports.                                                                   |
| I-8 | Re-importing the same decision must**update**, not duplicate. Define and document how a decision is uniquely identified.                                                                                                       |
| I-9 | Bulk actions where they make sense (publish a batch, re-assign a category) — with the same audit trail.                                                                                                                             |

---

## 2. Admin — Clients

| #   | Requirement                                                                                                                   |
| --- | ----------------------------------------------------------------------------------------------------------------------------- |
| C-1 | Full CRUD on client accounts: create, view, modify, suspend, delete.                                                          |
| C-2 | Suspension is immediate — a suspended account loses access on its next request, not at its next login.                       |
| C-3 | Roles and permissions are explicit and visible. An admin must be able to answer "what can this account see?" from one screen. |
| C-4 | Activity visible per client: last login, what they consulted, volume.                                                         |
| C-5 | Deleting a client must handle their personal data properly — see §6.                                                        |

---

## 3. Client space

| #   | Requirement                                                                                                                                                                                                                                                                                                |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S-1 | Login / signup with secure password handling, password reset, and session expiry. Whether signup is open or admin-approved is my decision — see §6.                                                                                                                                                      |
| S-2 | Browse by category — إدارية · تجارية · مدنية · جنائية · اجتماعية · أحوال شخصية · عقارية. Clear, calm, fast. This is the first screen and it sets the impression.                                                                                     |
| S-3 | Decisions listed in**sortable, filterable tables**: `رقم القرار`, `رقم الملف`, date, chamber, category. Filter by date range, chamber, category, at minimum.                                                                                                                    |
| S-4 | **View the source file** (pdf / doc / docx / image) in the browser — the anonymized version only.                                                                                                                                                                                                   |
| S-5 | **Full-text search** across decisions. Must work correctly in Arabic: results must be the same whether the user types `أ` or `ا`, `ي` or `ى`, with or without diacritics or tatweel, and with Arabic-Indic or ASCII digits. Search must stay fast as the corpus grows well beyond 2,000. |
| S-6 | Search results show why they matched (highlighted context), and support combining search with the §S-3 filters.                                                                                                                                                                                           |
| S-7 | Where a decision links to the one it overturns (`استئناف ← نقض`), the client can navigate between them in one click. This is the feature that makes the product worth paying for — treat it as a first-class part of the UI, not a footnote.                                                 |
| S-8 | Interface in Arabic with correct RTL layout throughout, including tables, search, and the document viewer. Plan for a French interface later.                                                                                                                                                              |
| S-9 | Usable on mobile and on a normal office screen.                                                                                                                                                                                                                                                            |

---

## 4. Rules (all three parts)

- **Least privilege** — a client can never reach an admin function, and no URL, identifier, or file path may be guessable into unauthorized access.
- **The original, non-anonymized documents never enter this platform.** Not in storage, not in a backup, not in a temporary folder.
- **Nothing published without human validation** (I-6).
- **Auditable** — for any published record, it must be possible to show where it came from, what was corrected, by whom, and when.
- **Resilient** — an import of thousands of records must not degrade the client experience while it runs.
- **Configurable, containerized, reproducible** — runs on a clean machine from a documented procedure.



## 6. Testing

- Automated tests, running in CI, covering each of the requirements above.
- **Permission tests are mandatory**: for every client-reachable route and file, prove that an unauthenticated user, a suspended user, and a normal client each get the right answer.
- **A test proving no client can obtain a non-anonymized document by any route.**
- Arabic search tested against a written list of query/expected-result pairs, including the spelling variants in S-5.
- Search and browse performance tested at 10× the current corpus, not at 2,000.
- 

## 7. Deliverables

Design note → working platform (3 parts) → automated test suite including the permission tests → deployment procedure and backup/restore procedure, both tested → admin documentation → a short operating guide for whoever will run the daily import and review.
