# Lovable Build Prompt — "Anonymize" (Arabic Legal-Document PII Platform)

Paste the section below into Lovable. It describes a full SaaS platform whose
frontend + auth + billing live in Lovable/Supabase, and whose heavy processing is
done by an **external Python REST API** (already built — the FastAPI service in
`backend/server.py`).

---

## 1) Product brief
Build **Anonymize**, a SaaS web platform for law firms, courts, and legal-tech teams
to **anonymize Personally Identifiable Information (PII) in Arabic legal documents**
(Moroccan court rulings) and **link related case documents across court levels**
(first instance → appeal → cassation / ابتدائي → استئناف → نقض).

A user uploads scanned PDFs, text PDFs, or Word files (.doc/.docx). The platform
sends them to the processing API, which returns: (1) anonymized `.docx` files with
all names/addresses/IDs replaced by `XXXXXXX`, (2) a **documents index** (each file
classified by court chamber), and (3) a **cases index** that groups documents of the
same case and shows its trajectory and whether it was appealed/cassated.

Tone: professional, trustworthy, "legal-grade". Must feel secure and precise.

## 2) Users & roles
- **Member** — upload, process, view/download their workspace's results.
- **Admin** (workspace owner) — everything + manage members, billing, API settings.
- (Optional) **Super-admin** — internal, sees all workspaces.

Multi-tenant: every user belongs to a **Workspace** (organization). All data is
scoped to a workspace with row-level security.

## 3) Architecture & integrations
- **Frontend:** React + Tailwind + shadcn/ui (Lovable default). **Full RTL support**
  (Arabic content) with an LTR app chrome; set `dir="rtl"` on Arabic text blocks.
- **Auth + DB + Storage:** Supabase (email/password + Google OAuth, magic link).
- **Processing API (external):** the Python FastAPI service. Configure its base URL as
  an env var `PROCESSING_API_URL` and an optional `PROCESSING_API_TOKEN` (sent as
  `Authorization: Bearer <token>`). Endpoints the frontend must call:

  | Method | Path | Purpose |
  |---|---|---|
  | POST | `/api/jobs` | multipart `files[]` (+ optional `gemini_api_key`) → `{job_id}` |
  | GET | `/api/jobs/{id}` | `{status: queued\|running\|done\|error, progress:{done,total,current}, totals, error}` |
  | GET | `/api/jobs/{id}/cases` | array of case rows (see schema below) |
  | GET | `/api/jobs/{id}/documents` | array of document rows |
  | GET | `/api/jobs/{id}/download` | zip (anonymized .docx + csvs) |
  | GET | `/health` | health check |

  **Flow:** on upload → POST `/api/jobs` → poll GET `/api/jobs/{id}` every ~1.5s and
  drive a progress bar from `progress.done/progress.total` → when `done`, fetch cases +
  documents and render; offer the download zip. Mirror job/case/document summaries into
  Supabase for history, usage, and cross-session access.

  **Cases row fields:** `case_id, category, levels_present, courts_passed,
  ibtidai_file, istinaf_file, naqd_file, appealed (نعم/لا), cassated (نعم/لا),
  missing_levels, docs, review (ok/check)`.
  **Document row fields:** `file, case_id, level, category, own_court, own_file_no,
  own_decision, date, refs_file_no, related_docs, appealed, cassated, pii_count`.

## 4) Authentication (must-have)
- Sign up / log in with **email+password** and **Google**; password reset; email verify.
- After first login → **onboarding**: create/name Workspace, choose plan (or start Free).
- Protected app routes; unauthenticated users see the marketing landing + auth pages.
- Session persistence, logout, "invite teammate by email" (Admin).

## 5) Pages & flows (detailed)

### Landing (public)
Hero: "Anonymize Arabic legal documents in seconds." Sub: PII redaction +
case-linkage across court levels. CTA: *Start free* / *Book demo*. Sections: how it
works (3 steps: Upload → Anonymize → Download/Link), supported inputs (Scanned PDF,
Text PDF, DOC/DOCX), security/compliance, pricing, FAQ, footer. Bilingual-friendly.

### Auth pages
Login, Signup, Forgot/Reset password, OAuth callback. Clean centered card.

### Dashboard (home, after login)
- KPI tiles: documents processed (this month), PII redacted, cases linked, usage vs quota.
- "New job" primary button. Recent jobs list (status chips). Quick links.

### New Job (upload)
- Drag-and-drop uploader (multi-file), accept `.pdf,.doc,.docx`; show file list w/ size + remove.
- Options: replacement token (default `XXXXXXX`), toggle "reprocess".
- (Advanced, collapsible) use my own Gemini key (passes `gemini_api_key`).
- **Start** → POST to API → redirect to Job Detail.

### Job Detail (live progress)
- **Progress bar** driven by polling; show `done/total` and the current file.
- Live per-document feed (file · level · chamber · PII · status), failures highlighted.
- On completion: summary metrics (docs, pages, PII, est. cost, failures) and tabs:
  - **Documents** — sortable/filterable table (chamber, level, PII count, review flag).
  - **Cases** — grouped table: case, category, **trajectory badges**
    (ابتدائي/استئناف/نقض shown as a stepper), appealed/cassated pills, `missing_levels`,
    `review=check` warning badge, member docs.
  - Download button (zip). Copy links.

### Case Explorer / Case Detail
- Click a case → visual **chain** (a horizontal stepper: ابتدائي → استئناف → نقض),
  each node shows court name, file number, decision number, date, outcome; greyed
  "missing" nodes for levels referenced but not uploaded. List of member documents,
  each opening a preview of the anonymized text (RTL).

### History
- All past jobs (paginated), filter by date/status, re-download, delete.

### Settings
- Profile (name, avatar, language). Workspace (name, members, invites, roles).
- Processing API health indicator. Default replacement token. Data retention control
  (auto-delete results after N days).

### Billing & Usage
- Current plan, usage meter (documents/pages this cycle), upgrade/downgrade.
- Stripe checkout + customer portal. Invoices. Quota-exceeded state with upsell.

### Admin
- Manage members/roles, workspace settings, audit log (who processed/downloaded what,
  when), usage analytics charts.

## 6) Supabase data model (with RLS: scope every row to workspace_id)
- `profiles(id, full_name, avatar_url, locale, created_at)`
- `workspaces(id, name, owner_id, plan, created_at)`
- `workspace_members(workspace_id, user_id, role)`
- `jobs(id, workspace_id, created_by, api_job_id, status, doc_count, page_count,
  pii_count, est_cost, created_at, finished_at)`
- `documents(id, job_id, workspace_id, file, case_id, level, category, own_file_no,
  own_decision, date, pii_count, review)`
- `cases(id, job_id, workspace_id, case_key, category, levels_present, courts_passed,
  appealed, cassated, missing_levels, review)`
- `usage(workspace_id, period, documents, pages)`
- `subscriptions(workspace_id, stripe_customer_id, stripe_sub_id, plan, status, period_end)`
- `audit_log(id, workspace_id, actor_id, action, target, meta, created_at)`

## 7) Design system
- **Brand:** trustworthy legal-tech. Primary deep indigo/navy `#1E3A5F`, accent teal
  `#0E9F9A`, success green, warning amber (for `review=check`), danger red.
- Neutral slate grays; generous whitespace; rounded-xl cards; subtle shadows.
- **Typography:** Inter for UI (LTR); a clean Arabic face (e.g. "IBM Plex Sans Arabic"
  or "Cairo") for Arabic content, right-aligned, `dir="rtl"`, comfortable line-height.
- **Dark + light** themes (respect system, with toggle).
- Components: data tables with sticky headers + filters, status chips, a **court-level
  stepper** component (ابتدائي → استئناف → نقض with done/missing states), progress bar,
  toasts, empty states, skeleton loaders.
- Motion: subtle; progress and stepper animate. Accessible (WCAG AA, keyboard, focus).

## 8) Monetization
- Plans: **Free** (e.g. 50 docs/mo), **Pro** (metered, higher quota), **Firm/Team**
  (seats + volume + priority). Meter by **documents** (and show pages).
- Stripe subscriptions + usage display + quota enforcement (block/queue when exceeded,
  with upgrade CTA). Show estimated cost per job.

## 9) Security & compliance (critical — legal PII)
- All data workspace-scoped via RLS; least-privilege.
- Encrypt at rest (Supabase) and in transit (HTTPS). Signed, expiring download URLs.
- **Data retention controls** + one-click delete of a job's documents.
- Audit log of processing/downloads. Clear privacy copy. Never expose other tenants' data.
- Note in UI when a document could not be fully matched (`review=check`) so a human verifies.

## 10) Env / config
- `PROCESSING_API_URL`, `PROCESSING_API_TOKEN` (optional), Supabase URL/anon key,
  Stripe keys. Never hardcode secrets; use Lovable/Supabase secrets.

## 11) MVP acceptance criteria
1. User can sign up, verify, log in (email + Google), create a workspace.
2. Upload `.pdf/.doc/.docx`, start a job, see **live progress**, and get results.
3. **Documents** and **Cases** tables render with chamber classification and the
   court-level trajectory; `appealed`/`cassated`/`missing_levels`/`review` shown.
4. Case Explorer visualizes the chain (stepper with missing nodes).
5. Download zip of anonymized docs + CSVs.
6. History, usage meter, plan/billing, roles/invites, audit log.
7. Fully responsive, dark/light, RTL-correct Arabic, WCAG AA.

Build it page-by-page starting with auth + dashboard + New Job + Job Detail (the core
loop), then Cases/Case Explorer, then billing/admin.
