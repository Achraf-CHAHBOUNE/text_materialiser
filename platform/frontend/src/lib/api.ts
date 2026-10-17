// API client for the anonymized-decisions platform (Project 2).
// Client space: browse / search / view published decisions.
// Admin: import (with gate), review/correct/publish, client accounts.

import type { Lang } from "./lang-url";

const BASE = (import.meta.env["VITE_API_URL"] ?? "http://localhost:8000").replace(/\/$/, "");
// The session is an HttpOnly cookie the server sets at sign-in: no script on the page
// can read it, and file links need no token in their address. What is kept here is
// only who is signed in -- a hint for the interface; the cookie decides.
const LEGACY_TOKEN_KEY = "anon-token"; // pages before the cookie kept the token here
const EMAIL_KEY = "anon-email";
const ROLE_KEY = "anon-role";

function readStore(key: string): string {
  try {
    return (typeof window !== "undefined" ? window.localStorage.getItem(key) : null) || "";
  } catch {
    return ""; // storage blocked: treated as signed out
  }
}
function writeStore(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the cookie still holds the session */
  }
}

export const getEmail = () => readStore(EMAIL_KEY);
export const getRole = () => readStore(ROLE_KEY);
export const isAuthed = () => !!getEmail();
export const isAdmin = () => getRole() === "admin";
export function clearAuth() {
  writeStore(LEGACY_TOKEN_KEY, null);
  writeStore(EMAIL_KEY, null);
  writeStore(ROLE_KEY, null);
}

/** A browser signed in before the cookie existed still holds its token: hand it to the
 *  server once for the cookie of the same session, then forget it. Nobody is signed out. */
export async function adoptLegacySession(): Promise<void> {
  const token = readStore(LEGACY_TOKEN_KEY);
  if (!token) return;
  try {
    const r = await fetch(BASE + "/api/auth/session", {
      method: "POST",
      credentials: "include",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (r.status === 401 || r.status === 403) clearAuth();
  } catch {
    /* offline: tried again next time */
    return;
  }
  writeStore(LEGACY_TOKEN_KEY, null);
}

export type Level = "ابتدائي" | "استئناف" | "نقض" | "";
export type Review = "ok" | "check";
export type PubState = "imported" | "under_review" | "published" | "withdrawn";

export type Decision = {
  doc_id: string;
  source_file: string;
  format: string;
  category: string;
  level: Level;
  court: string;
  decision_no: string;
  file_no: string;
  date: string;
  city?: string;
  year?: string;
  version?: number;
  edited_at?: string;
  edited_by?: string;
  case_id: string;
  outcome: string;
  pii_removed: number;
  review: Review;
  state: PubState;
  file_name: string;
  updated_at: string;
  // the court's own headnote, empty when the ruling prints none
  theme?: string;
  keywords?: string;
  rule?: string;
  theme_source?: string;
  abstract?: string;
  theme_key?: string;
  // In French (only when asked with lang=fr). The Arabic fields above are never
  // replaced; an empty one here means that part has no French yet.
  theme_fr?: string;
  keywords_fr?: string;
  abstract_fr?: string;
  abstract_fr_of?: "rule" | "abstract" | "";
  has_fr?: boolean;
  body_text?: string;
  snippets?: string[];
  reasons?: string[];
  review_notes?: string[];
  links?: { to: string; role: "reviews" | "reviewed_by"; confidence: string }[];
  audit?: { ts: string; actor: string; action: string; field: string; old: string; new: string }[];
};

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const r = await fetch(BASE + path, { ...init, headers, credentials: "include" });
  if (r.status === 401 && isAuthed()) {
    // signed out elsewhere, or the session ended: back to the sign-in page
    clearAuth();
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("session-ended"));
  }
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    if (r.status === 402 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("subscription-lapsed", { detail: body.detail }));
    }
    throw new ApiError(r.status, detailText(body.detail, r.status), body.detail);
  }
  return (await r.json()) as T;
}
const j = request;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

/** The server's reason, readable: some refusals carry a structure, not a sentence. */
function detailText(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (Array.isArray(d["gate"]))
      return `Personal data found: ${(d["gate"] as string[]).join(" · ")}`;
    if (d["fields"] && typeof d["fields"] === "object") {
      return Object.entries(d["fields"] as Record<string, string>)
        .map(([k, v]) => `${k}: ${v}`)
        .join(" · ");
    }
  }
  return `HTTP ${status}`;
}

// ---------- auth ----------
/** Thrown when the password was right and the account wants its six-digit code. */
export class NeedsCode extends Error {
  constructor(public wrong: boolean) {
    super(wrong ? "wrong code" : "code required");
  }
}

export async function login(email: string, password: string, code = "") {
  const r = await fetch(BASE + "/api/auth/login", {
    method: "POST",
    credentials: "include", // the answer sets the session cookie
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, code }),
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    if (detail && typeof detail === "object" && (detail as { mfa?: boolean }).mfa) {
      throw new NeedsCode(Boolean((detail as { wrong?: boolean }).wrong));
    }
    throw new Error(typeof detail === "string" ? detail : "Invalid email or password");
  }
  const data = (await r.json()) as { email: string; role: string; language?: string };
  writeStore(LEGACY_TOKEN_KEY, null);
  writeStore(EMAIL_KEY, data.email);
  writeStore(ROLE_KEY, data.role);
  return data;
}

export const apiBase = BASE;

/** End this session on the server too, so the token cannot be reused. */
export async function logoutRemote() {
  try {
    await j<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
  } catch {
    /* already ended: nothing to do */
  }
}

// ---------- client space ----------
export const getCategories = () => j<string[]>("/api/categories");

type Page = { category?: string; level?: string; limit?: number; offset?: number };

export function listDecisions(p: Page = {}) {
  const q = new URLSearchParams();
  if (p.category) q.set("category", p.category);
  if (p.level) q.set("level", p.level);
  q.set("limit", String(p.limit ?? 50));
  q.set("offset", String(p.offset ?? 0));
  return j<Decision[]>(`/api/decisions?${q}`);
}

export function searchDecisions(query: string, p: Page = {}) {
  const q = new URLSearchParams({ q: query });
  if (p.category) q.set("category", p.category);
  if (p.level) q.set("level", p.level);
  q.set("limit", String(p.limit ?? 50));
  q.set("offset", String(p.offset ?? 0));
  return j<Decision[]>(`/api/search?${q}`);
}

export const getDecision = (id: string, lang: Lang = "ar") =>
  j<Decision>(`/api/decisions/${encodeURIComponent(id)}?lang=${lang}`);
export const decisionFileUrl = (id: string) =>
  `${BASE}/api/decisions/${encodeURIComponent(id)}/file`;

// ---------- admin ----------
/** An uploaded delivery: imported during the upload when small, by the worker when large. */
export type ImportJob = {
  id: number;
  file_name: string;
  size: number;
  status: "queued" | "running" | "done" | "failed";
  error: string;
  created_by: string;
  created_at: string;
  finished_at: string;
  total_records?: number;
  read?: number;
  to_read?: number;
  imported?: number;
  updated?: number;
  kept_edited?: number;
  held_by_pipeline?: number;
  no_file?: number;
  gate_quarantined?: number;
  unreadable?: number;
  with_subject?: number;
  with_rule?: number;
  with_outcome?: number;
  rejected?: { doc_id: string; reason: string }[];
  quarantined?: { doc_id: string; findings: string[] }[];
};
export async function importBatch(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return j<ImportJob>("/api/admin/import", { method: "POST", body: fd });
}
export const importJobs = () => j<ImportJob[]>("/api/admin/import/jobs");
export const importJob = (id: number) => j<ImportJob>(`/api/admin/import/jobs/${id}`);

export const adminStats = () =>
  j<{ decisions: number; published: number; pending: number; clients: number }>("/api/admin/stats");
export const adminQueue = () => j<Decision[]>("/api/admin/queue");
export const adminGetDecision = (id: string) =>
  j<Decision>(`/api/admin/decisions/${encodeURIComponent(id)}`);
export const correctDecision = (id: string, changes: Record<string, string>) =>
  j<Decision>(`/api/admin/decisions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ changes }),
  });
export const setDecisionState = (id: string, state: PubState) =>
  j<Decision>(`/api/admin/decisions/${encodeURIComponent(id)}/state`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state }),
  });
export const adminFileUrl = (id: string) =>
  `${BASE}/api/admin/decisions/${encodeURIComponent(id)}/file`;

// ---------- browse: court > chamber > year > ruling ----------
// Mirrors how a court portal is read (the JURISMAROC layout the client asked for).
export type CourtNode = {
  court: string;
  total: number;
  chambers: { chamber: string; count: number }[];
};
export type YearCount = { year: string; count: number };
export type CityCount = { city: string; count: number };
export type ListingRow = {
  doc_id: string;
  decision_no: string;
  date: string; // DD/MM/YYYY
  city: string;
  chamber: string;
  court: string;
  year: string;
  case_id: string;
  file_no: string;
  // What the court printed above the ruling, and what the Cassation portal shows in
  // its "المفاتيح أو القاعدة أو المحتوى" column: the subject chain, and the rule.
  // Empty for the roughly half of rulings that print no headnote.
  theme: string;
  theme_key: string;
  keywords: string;
  rule: string; // an opening excerpt, cut server-side
  // "court" when the subject was printed on the ruling, "model" when it was written
  // for us. `rule` is only ever the court's; `abstract` is only ever ours.
  theme_source: string;
  abstract: string;
  // In French (only when asked with lang=fr). The Arabic fields above are never
  // replaced; an empty one here means that part has no French yet.
  theme_fr?: string;
  keywords_fr?: string;
  abstract_fr?: string;
  abstract_fr_of?: "rule" | "abstract" | "";
  has_fr?: boolean;
};
// label is in the language asked for; label_ar is the court's wording, when different
export type ThemeCount = { key: string; label: string; label_ar?: string; count: number };

export const browseCourts = () => j<CourtNode[]>("/api/browse/courts");

export const browseYears = (chamber = "") =>
  j<YearCount[]>(`/api/browse/years?chamber=${encodeURIComponent(chamber)}`);

export const browseCities = (chamber = "") =>
  j<CityCount[]>(`/api/browse/cities?chamber=${encodeURIComponent(chamber)}`);

export const browseThemes = (chamber = "", lang: Lang = "ar") =>
  j<ThemeCount[]>(`/api/browse/themes?chamber=${encodeURIComponent(chamber)}&lang=${lang}`);

export function browseRulings(
  p: {
    chamber?: string | undefined;
    year?: string | undefined;
    city?: string | undefined;
    q?: string | undefined;
    theme?: string | undefined;
    limit?: number;
    offset?: number;
    lang?: Lang;
  } = {},
) {
  const q = new URLSearchParams();
  if (p.chamber) q.set("chamber", p.chamber);
  if (p.year) q.set("year", p.year);
  if (p.city) q.set("city", p.city);
  if (p.theme) q.set("theme", p.theme);
  if (p.q) q.set("q", p.q);
  q.set("limit", String(p.limit ?? 50));
  q.set("offset", String(p.offset ?? 0));
  q.set("lang", p.lang ?? "ar");
  return j<{ total: number; items: ListingRow[] }>(`/api/browse/rulings?${q}`);
}

// ---------- editing a ruling (admin) ----------
// Hiding goes live at once; anything that adds text becomes a draft to approve.
// Every mutation sends the version it was made on: a stale one is refused (409).
export type DiffHunk = { line: number; segments: { op: "equal" | "del" | "ins"; text: string }[] };
export type VersionRow = {
  id: number;
  doc_id: string;
  version: number | null;
  status: "applied" | "draft" | "discarded";
  action: string;
  summary: string;
  actor: string;
  created_at: string;
  base_version: number;
  restore_of: number | null;
  decided_by: string;
  decided_at: string;
  decision_no?: string;
  category?: string;
};
export type ReportRow = {
  id: number;
  doc_id: string;
  decision_no: string;
  category: string;
  reporter: string;
  quote: string;
  note: string;
  status: "open" | "resolved" | "dismissed";
  created_at: string;
};
export type History = { versions: VersionRow[]; drafts: VersionRow[]; reports?: ReportRow[] };
export type EditOutcome = {
  applied: boolean;
  version?: number;
  draft_id?: number;
  deleted?: number;
  decision: Decision;
  history: History;
};

const post = <T>(path: string, body?: unknown) =>
  j<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
const dec = (id: string) => `/api/admin/decisions/${encodeURIComponent(id)}`;

export const rulingHistory = (id: string) => j<History>(`${dec(id)}/history`);

export const hideText = (
  id: string,
  p: { value: string; base_version: number; occurrence?: number },
) => post<EditOutcome>(`${dec(id)}/hide`, p);
export const previewHideAll = (id: string, value: string, base_version: number) =>
  post<{ count: number; snippets: string[] }>(`${dec(id)}/hide`, {
    value,
    base_version,
    everywhere: true,
    dry_run: true,
  });
export const hideAll = (id: string, value: string, base_version: number) =>
  post<EditOutcome>(`${dec(id)}/hide`, { value, base_version, everywhere: true });

export const previewText = (id: string, text: string, base_version: number) =>
  post<{ removal: boolean; summary: string; diff: DiffHunk[]; gate: string[] }>(`${dec(id)}/text`, {
    text,
    base_version,
    dry_run: true,
  });
export const saveText = (id: string, text: string, base_version: number) =>
  post<EditOutcome>(`${dec(id)}/text`, { text, base_version });

export const versionDiff = (id: string, version: number) =>
  j<{ removal: boolean; diff: DiffHunk[] }>(`${dec(id)}/versions/${version}`);
export const restoreVersion = (id: string, version: number, base_version: number) =>
  post<EditOutcome>(`${dec(id)}/restore`, { version, base_version });
export const purgeHistory = (id: string) => post<EditOutcome>(`${dec(id)}/purge-history`);

export const listDrafts = () => j<VersionRow[]>("/api/admin/drafts");
export const getDraft = (draftId: number) =>
  j<VersionRow & { stale: boolean; diff: DiffHunk[]; gate: string[] }>(
    `/api/admin/drafts/${draftId}`,
  );
export const approveDraft = (draftId: number) =>
  post<EditOutcome>(`/api/admin/drafts/${draftId}/approve`);
export const discardDraft = (draftId: number) =>
  post<EditOutcome>(`/api/admin/drafts/${draftId}/discard`);

export const listReports = (status = "open") =>
  j<ReportRow[]>(`/api/admin/reports?status=${encodeURIComponent(status)}`);
export const resolveReport = (reportId: number, status: "resolved" | "dismissed") =>
  post<{ ok: boolean }>(`/api/admin/reports/${reportId}`, { status });
export const editsExportUrl = () => `${BASE}/api/admin/edits/export`;

// ---------- reading a ruling in French ----------
// Translated once, then stored: the first reader waits a few seconds, everyone after
// gets it instantly. "stale" means the ruling was corrected after it was translated.
export type Translation = {
  ready: boolean;
  lang?: string;
  text?: string;
  model?: string;
  created_at?: string;
  stale?: boolean;
  // the headnote in French, when there is one (empty strings otherwise)
  theme_fr?: string;
  keywords_fr?: string;
  abstract_fr?: string;
  abstract_fr_of?: "rule" | "abstract" | "";
};

export const getTranslation = (id: string) =>
  j<Translation>(`/api/decisions/${encodeURIComponent(id)}/translation?lang=fr`);
export const makeTranslation = (id: string) =>
  post<Translation>(`/api/decisions/${encodeURIComponent(id)}/translation?lang=fr`);

// ---------- a reader reports a problem ----------
export const reportProblem = (id: string, quote: string, note: string) =>
  post<{ id: number }>(`/api/decisions/${encodeURIComponent(id)}/reports`, { quote, note });
