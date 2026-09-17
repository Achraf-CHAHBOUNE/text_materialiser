// API client for the anonymized-decisions platform (Project 2).
// Client space: browse / search / view published decisions.
// Admin: import (with gate), review/correct/publish, client accounts.

const BASE = (import.meta.env["VITE_API_URL"] ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "anon-token";
const EMAIL_KEY = "anon-email";
const ROLE_KEY = "anon-role";

export const getToken = () =>
  (typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_KEY) : null) || "";
export const getEmail = () =>
  (typeof window !== "undefined" ? window.localStorage.getItem(EMAIL_KEY) : null) || "";
export const getRole = () =>
  (typeof window !== "undefined" ? window.localStorage.getItem(ROLE_KEY) : null) || "";
export const isAuthed = () => !!getToken();
export const isAdmin = () => getRole() === "admin";
export function clearAuth() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(EMAIL_KEY);
  window.localStorage.removeItem(ROLE_KEY);
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
  body_text?: string;
  snippets?: string[];
  reasons?: string[];
  review_notes?: string[];
  links?: { to: string; role: "reviews" | "reviewed_by"; confidence: string }[];
  audit?: { ts: string; actor: string; action: string; field: string; old: string; new: string }[];
};

export type ClientAccount = {
  email: string;
  role: string;
  status: "active" | "suspended";
  created_at: string;
  last_login: string;
  recent_activity?: { ts: string; action: string; decision_id: string }[];
};

async function j<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(BASE + path, { ...init, headers });
  if (r.status === 401) clearAuth();
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new ApiError(r.status, detailText(body.detail, r.status));
  }
  return (await r.json()) as T;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** The server's reason, readable: some refusals carry a structure, not a sentence. */
function detailText(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (Array.isArray(d["gate"])) return `Personal data found: ${(d["gate"] as string[]).join(" · ")}`;
    if (d["fields"] && typeof d["fields"] === "object") {
      return Object.entries(d["fields"] as Record<string, string>).map(([k, v]) => `${k}: ${v}`).join(" · ");
    }
  }
  return `HTTP ${status}`;
}

// ---------- auth ----------
export async function login(email: string, password: string) {
  const r = await fetch(BASE + "/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Invalid email or password");
  const data = (await r.json()) as { token: string; email: string; role: string };
  window.localStorage.setItem(TOKEN_KEY, data.token);
  window.localStorage.setItem(EMAIL_KEY, data.email);
  window.localStorage.setItem(ROLE_KEY, data.role);
  return data;
}

const tokenQ = () => `token=${encodeURIComponent(getToken())}`;

// ---------- client space ----------
export const getCategories = () => j<string[]>("/api/categories");

export function listDecisions(p: { category?: string; level?: string; limit?: number } = {}) {
  const q = new URLSearchParams();
  if (p.category) q.set("category", p.category);
  if (p.level) q.set("level", p.level);
  q.set("limit", String(p.limit ?? 100));
  return j<Decision[]>(`/api/decisions?${q}`);
}

export function searchDecisions(query: string, p: { category?: string; level?: string } = {}) {
  const q = new URLSearchParams({ q: query });
  if (p.category) q.set("category", p.category);
  if (p.level) q.set("level", p.level);
  return j<Decision[]>(`/api/search?${q}`);
}

export const getDecision = (id: string) => j<Decision>(`/api/decisions/${encodeURIComponent(id)}`);
export const decisionFileUrl = (id: string) =>
  `${BASE}/api/decisions/${encodeURIComponent(id)}/file?${tokenQ()}`;

// ---------- admin ----------
export async function importBatch(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return j<{ imported: number; updated: number; total_records: number;
    rejected: { doc_id: string; reason: string }[];
    quarantined: { doc_id: string; findings: string[] }[] }>(
    "/api/admin/import", { method: "POST", body: fd });
}

export const adminStats = () =>
  j<{ decisions: number; published: number; pending: number; clients: number }>("/api/admin/stats");
export const adminQueue = () => j<Decision[]>("/api/admin/queue");
export function adminListDecisions(p: { state?: string; category?: string; level?: string } = {}) {
  const q = new URLSearchParams();
  if (p.state) q.set("state", p.state);
  if (p.category) q.set("category", p.category);
  if (p.level) q.set("level", p.level);
  return j<Decision[]>(`/api/admin/decisions?${q}`);
}
export const adminGetDecision = (id: string) =>
  j<Decision>(`/api/admin/decisions/${encodeURIComponent(id)}`);
export const correctDecision = (id: string, changes: Record<string, string>) =>
  j<Decision>(`/api/admin/decisions/${encodeURIComponent(id)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ changes }),
  });
export const setDecisionState = (id: string, state: PubState) =>
  j<Decision>(`/api/admin/decisions/${encodeURIComponent(id)}/state`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state }),
  });
export const adminFileUrl = (id: string) =>
  `${BASE}/api/admin/decisions/${encodeURIComponent(id)}/file?${tokenQ()}`;

export const listClients = () => j<ClientAccount[]>("/api/admin/clients");
export const createClient = (email: string, password: string) =>
  j<ClientAccount>("/api/admin/clients", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
export const updateClient = (email: string, body: { status?: string; password?: string }) =>
  j<ClientAccount>(`/api/admin/clients/${encodeURIComponent(email)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const deleteClient = (email: string) =>
  j<{ deleted: string }>(`/api/admin/clients/${encodeURIComponent(email)}`, { method: "DELETE" });

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
  date: string;      // DD/MM/YYYY
  city: string;
  chamber: string;
  court: string;
  year: string;
  case_id: string;
};

export const browseCourts = () => j<CourtNode[]>("/api/browse/courts");

export const browseYears = (chamber = "") =>
  j<YearCount[]>(`/api/browse/years?chamber=${encodeURIComponent(chamber)}`);

export const browseCities = (chamber = "") =>
  j<CityCount[]>(`/api/browse/cities?chamber=${encodeURIComponent(chamber)}`);

export function browseRulings(p: {
  chamber?: string | undefined; year?: string | undefined;
  city?: string | undefined; q?: string | undefined;
  limit?: number; offset?: number;
} = {}) {
  const q = new URLSearchParams();
  if (p.chamber) q.set("chamber", p.chamber);
  if (p.year) q.set("year", p.year);
  if (p.city) q.set("city", p.city);
  if (p.q) q.set("q", p.q);
  q.set("limit", String(p.limit ?? 50));
  q.set("offset", String(p.offset ?? 0));
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

const post = <T,>(path: string, body?: unknown) =>
  j<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
const dec = (id: string) => `/api/admin/decisions/${encodeURIComponent(id)}`;

export const rulingHistory = (id: string) => j<History>(`${dec(id)}/history`);

export const hideText = (id: string, p: { value: string; base_version: number; occurrence?: number }) =>
  post<EditOutcome>(`${dec(id)}/hide`, p);
export const previewHideAll = (id: string, value: string, base_version: number) =>
  post<{ count: number; snippets: string[] }>(`${dec(id)}/hide`,
    { value, base_version, everywhere: true, dry_run: true });
export const hideAll = (id: string, value: string, base_version: number) =>
  post<EditOutcome>(`${dec(id)}/hide`, { value, base_version, everywhere: true });

export const previewText = (id: string, text: string, base_version: number) =>
  post<{ removal: boolean; summary: string; diff: DiffHunk[]; gate: string[] }>(
    `${dec(id)}/text`, { text, base_version, dry_run: true });
export const saveText = (id: string, text: string, base_version: number) =>
  post<EditOutcome>(`${dec(id)}/text`, { text, base_version });

export const versionDiff = (id: string, version: number) =>
  j<{ removal: boolean; diff: DiffHunk[] }>(`${dec(id)}/versions/${version}`);
export const restoreVersion = (id: string, version: number, base_version: number) =>
  post<EditOutcome>(`${dec(id)}/restore`, { version, base_version });
export const purgeHistory = (id: string) => post<EditOutcome>(`${dec(id)}/purge-history`);

export const listDrafts = () => j<VersionRow[]>("/api/admin/drafts");
export const getDraft = (draftId: number) =>
  j<VersionRow & { stale: boolean; diff: DiffHunk[]; gate: string[] }>(`/api/admin/drafts/${draftId}`);
export const approveDraft = (draftId: number) => post<EditOutcome>(`/api/admin/drafts/${draftId}/approve`);
export const discardDraft = (draftId: number) => post<EditOutcome>(`/api/admin/drafts/${draftId}/discard`);

export const listReports = (status = "open") =>
  j<ReportRow[]>(`/api/admin/reports?status=${encodeURIComponent(status)}`);
export const resolveReport = (reportId: number, status: "resolved" | "dismissed") =>
  post<{ ok: boolean }>(`/api/admin/reports/${reportId}`, { status });
export const editsExportUrl = () => `${BASE}/api/admin/edits/export?${tokenQ()}`;

// ---------- a reader reports a problem ----------
export const reportProblem = (id: string, quote: string, note: string) =>
  post<{ id: number }>(`/api/decisions/${encodeURIComponent(id)}/reports`, { quote, note });
