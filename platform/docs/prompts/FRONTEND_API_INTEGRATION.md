# Lovable — wire the app to the Anonymize backend API

Connect the existing app to the real backend (FastAPI). Keep the current design and
routes; just replace the mock/simulated flow with live API calls. The backend contract
and exact field mapping are below.

## 1) Env
Add a Vite env var for the API base URL:
```
# .env
VITE_API_URL=http://localhost:8000
```
(Use your deployed backend URL in production. CORS is already open on the backend.)

## 2) Add `src/lib/api.ts`
```ts
import type { CaseRow, DocRow, Level, Review } from "./mock-data";

const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type JobStatus = {
  job_id: string;
  status: "queued" | "running" | "done" | "error";
  progress: { done?: number; total?: number; current?: string; ok?: boolean };
  totals: { documents?: number; pages?: number; pii?: number; cost?: number; failed?: number };
  error?: string;
  documents?: number;
};

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, init);
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json() as Promise<T>;
}

export async function createJob(files: File[]): Promise<{ job_id: string }> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  return j("/api/jobs", { method: "POST", body: fd });
}
export const getJob = (id: string) => j<JobStatus>(`/api/jobs/${id}`);
export const downloadUrl = (id: string) => `${BASE}/api/jobs/${id}/download`;

const splitLevels = (s: string): Level[] =>
  (s || "").split(/[،,]/).map((x) => x.trim()).filter(Boolean) as Level[];
const rev = (r: string): Review => (r === "check" ? "check" : "ok");

export async function getCases(id: string): Promise<CaseRow[]> {
  const rows = await j<any[]>(`/api/jobs/${id}/cases`);
  return rows.map((c) => ({
    id: c.case_id,
    chamber: c.category,
    trajectory: splitLevels(c.levels_present),
    appealed: c.appealed === "نعم",
    cassated: c.cassated === "نعم",
    missing: splitLevels(c.missing_levels),
    review: rev(c.review),
  }));
}

export async function getDocuments(id: string): Promise<DocRow[]> {
  const rows = await j<any[]>(`/api/jobs/${id}/documents`);
  return rows.map((d) => ({
    file: d.file,
    level: d.level as Level,
    chamber: d.category,
    pii: Number(d.pii_count) || 0,
    review: rev(d.review),
    caseId: d.case_id,
  }));
}
```

## 3) Rewire `src/lib/app-store.tsx`
- Add state: `cases: CaseRow[]`, `documents: DocRow[]`, `jobId: string | null`, `error: string | null`.
- Replace the fake-timer `startJob` with a real one that takes the selected `File[]`:
  1. `const { job_id } = await createJob(files)` → save `jobId`, set `running=true`.
  2. Poll `getJob(job_id)` every ~1.2s: update `progress` (`status.progress.done/total`) and append to `feed` using the `current` doc; on `status==="done"` → `documents = await getDocuments(job_id)`, `cases = await getCases(job_id)`, `hasResults=true`, `running=false`; on `error` → set `error`, `running=false`.
- Keep the uploaded browser `File` objects (not just name/size) so they can be sent — extend `UploadFile` to hold the real `File`, or store a parallel `File[]`.
- Expose `cases`, `documents`, `jobId`, `error`, and `downloadUrl(jobId)` from the store.

## 4) Point pages at the store (fallback to mock when empty)
- `src/routes/results.tsx`: use `store.documents.length ? store.documents : documents` and
  `store.cases.length ? store.cases : cases`.
- `src/routes/cases.$caseId.tsx`: look the case up in `store.cases` first, then mock.
- `src/routes/processing.tsx`: already reads `progress`/`feed` from the store — no change.
- Download button → `window.open(downloadUrl(store.jobId!))`.

## 5) Backend contract (reference)
```
POST /api/jobs                 multipart files[]        -> { job_id, status, documents }
GET  /api/jobs/{id}            -> { status, progress:{done,total,current,ok}, totals, error }
GET  /api/jobs/{id}/documents  -> [ {file, level, category, court, pii_count, case_id, review} ]
GET  /api/jobs/{id}/cases      -> [ {case_id, category, levels_present, courts_passed,
                                     ibtidai_file, istinaf_file, naqd_file,
                                     appealed:"نعم"/"لا", cassated, missing_levels, docs, review} ]
GET  /api/jobs/{id}/download   -> application/zip (anonymized .docx + csvs)
```
Notes: `levels_present`/`missing_levels` are Arabic-comma (،) separated. `appealed`/`cassated`
are `"نعم"`/`"لا"`. Court-stepper file numbers come from `ibtidai_file/istinaf_file/naqd_file`.

## Acceptance
Uploading real files runs the live backend (progress bar tracks real job progress), the
Results tables show real Documents + Cases, clicking a case opens the stepper, and Download
returns the anonymized `.docx` + CSVs. Falls back to mock data only when no job has run.
