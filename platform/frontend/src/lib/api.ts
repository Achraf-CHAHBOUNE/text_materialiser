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
  if (r.status === 401 || r.status === 403) {
    if (r.status === 401) clearAuth();
    throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `API ${r.status}`);
  return (await r.json()) as T;
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
