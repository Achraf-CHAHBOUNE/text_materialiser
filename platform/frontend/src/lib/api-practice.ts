// The firm module (cabinet): a law firm's own clients, cases, hearings, deadlines,
// documents, time, expenses and fee notes. Only the firm's members can reach it.
import { apiBase, getToken, request as j } from "./api";
import type { Lang } from "./lang-url";

const send = <T,>(method: string, path: string, body?: unknown) =>
  j<T>(`/api/practice${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
const get = <T,>(path: string) => j<T>(`/api/practice${path}`);
const qs = (o: Record<string, string | number | boolean | undefined | null>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => [k, String(v)])).toString();

export type Level = "ابتدائي" | "استئناف" | "نقض" | "";
export type PClient = {
  id: number; kind: "person" | "company"; full_name: string; cin: string; ice: string; phone: string;
  email: string; address: string; city: string; notes: string; created_by: string; created_at: string;
  open_matters?: number;
};
export type Matter = {
  id: number; reference: string; title: string; client_id: number | null; client_role: string;
  opposing_party: string; opposing_lawyer: string; court: string; chamber: string; city: string;
  level: Level; case_number: string; kind: string; status: "open" | "closed" | "archived";
  responsible: string; opened_on: string; closed_on: string | null; fee_agreement: string; notes: string;
  client_name?: string; next_hearing?: string; next_deadline?: string;
};
export type Hearing = { id: number; matter_id: number; date: string; time: string; court: string; room: string;
  purpose: string; outcome: string; created_by: string; matter_reference?: string; matter_title?: string };
export type Deadline = { id: number; matter_id: number; kind: string; start_on: string; days: number; due_on: string;
  note: string; verified_by: string; done_at: string | null; matter_reference?: string; matter_title?: string };
export type PTask = { id: number; matter_id: number | null; title: string; due_on: string; assigned_to: string;
  done_at: string | null; matter_reference?: string; matter_title?: string };
export type Doc = { id: number; matter_id: number; name: string; size: number; mime: string; uploaded_by: string; uploaded_at: string };
export type TimeEntry = { id: number; matter_id: number; date: string; minutes: number; description: string;
  rate: number; user: string; fee_invoice_id: number | null };
export type Expense = { id: number; matter_id: number; date: string; label: string; amount: number; user: string;
  fee_invoice_id: number | null };
export type FeeNote = {
  id: number; number: string; client_id: number | null; matter_id: number | null; client_name: string;
  lines: { label: string; amount: number }[]; amount_ht: number; vat_rate: number; vat: number; amount_ttc: number;
  paid: number; balance: number; issued_on: string; due_on: string; status: "sent" | "paid" | "overdue" | "cancelled";
};
export type FeeDetail = FeeNote & {
  client: PClient | null; matter: { reference: string; title: string; case_number: string } | null;
  payments: { amount: number; method: string; reference: string; paid_on: string }[];
  firm: { name: string; address: string; city: string; ice: string; phone: string; email: string } | null;
};
export type LinkedRuling = { id: number; doc_id: string; note: string; added_by: string; decision_no: string;
  date: string; chamber: string; abstract: string; abstract_fr: string };
export type MatterDetail = Matter & {
  client: PClient | null; hearings: Hearing[]; deadlines: Deadline[]; tasks: PTask[]; documents: Doc[];
  time: TimeEntry[]; expenses: Expense[]; rulings: LinkedRuling[]; fee_invoices: FeeNote[]; unbilled: number;
};
export type Agenda = { from: string; to: string; hearings: Hearing[]; deadlines: Deadline[]; tasks: PTask[] };
export type FirmDashboard = {
  open_matters: number; clients: number; hearings_today: number; hearings_week: number;
  deadlines_late: number; deadlines_soon: number; deadlines_unverified: number; my_tasks_due: number;
  fees_unpaid: number; fees_overdue: number; collected_month: number; agenda: Agenda;
};

export const firmDashboard = () => get<FirmDashboard>("/dashboard");
export const firmAgenda = (start: string, days: number, mine: boolean) =>
  get<Agenda>(`/agenda?${qs({ start, days, mine })}`);
export const firmMembers = () => get<{ email: string; full_name: string }[]>("/members");
export const firmSearch = (q: string) => get<{ clients: PClient[]; matters: Matter[] }>(`/search?${qs({ q })}`);

export const pClients = (q = "") => get<PClient[]>(`/clients?${qs({ q })}`);
export const pClient = (id: number) => get<PClient & { matters: Matter[]; fee_invoices: FeeNote[] }>(`/clients/${id}`);
export const createPClient = (b: Partial<PClient>) => send<PClient>("POST", "/clients", b);
export const updatePClient = (id: number, b: Partial<PClient>) => send<PClient>("PATCH", `/clients/${id}`, b);
export const erasePClient = (id: number) => send<{ ok: boolean; matters: number; files: number }>("DELETE", `/clients/${id}`);

export const matters = (p: { q?: string; status?: string; client_id?: number; responsible?: string } = {}) =>
  get<Matter[]>(`/matters?${qs(p)}`);
export const matter = (id: number, lang: Lang) => get<MatterDetail>(`/matters/${id}?lang=${lang}`);
export const createMatter = (b: Partial<Matter>) => send<Matter>("POST", "/matters", b);
export const updateMatter = (id: number, b: Partial<Matter>) => send<Matter>("PATCH", `/matters/${id}`, b);
export const eraseMatter = (id: number) => send<{ ok: boolean }>("DELETE", `/matters/${id}`);

export const addHearing = (matterId: number, b: Partial<Hearing>) => send<Hearing>("POST", `/matters/${matterId}/hearings`, b);
export const updateHearing = (id: number, b: Partial<Hearing> & { next_date?: string }) => send<Hearing>("PATCH", `/hearings/${id}`, b);
export const deleteHearing = (id: number) => send<{ ok: boolean }>("DELETE", `/hearings/${id}`);
export const deadlinePresets = () => get<Record<string, number>>("/deadline-presets");
export const addDeadline = (matterId: number, b: { kind: string; start_on: string; days?: number; note?: string }) =>
  send<Deadline>("POST", `/matters/${matterId}/deadlines`, b);
export const updateDeadline = (id: number, b: { done?: boolean; verified?: boolean; due_on?: string }) =>
  send<Deadline>("PATCH", `/deadlines/${id}`, b);
export const addTask = (b: { title: string; due_on: string; matter_id?: number; assigned_to?: string }) =>
  send<PTask>("POST", "/tasks", b);
export const updateTask = (id: number, b: { done?: boolean; due_on?: string }) => send<PTask>("PATCH", `/tasks/${id}`, b);

export async function uploadDocument(matterId: number, file: File): Promise<Doc> {
  const fd = new FormData();
  fd.append("file", file);
  return j<Doc>(`/api/practice/matters/${matterId}/documents`, { method: "POST", body: fd });
}
export const deleteDocument = (id: number) => send<{ ok: boolean }>("DELETE", `/documents/${id}`);
export async function downloadDocument(id: number, name: string) {
  const r = await fetch(`${apiBase}/api/practice/documents/${id}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await r.blob());
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

export const linkRuling = (matterId: number, docId: string, note = "") =>
  send<{ ok: boolean; already?: boolean }>("POST", `/matters/${matterId}/rulings`, { doc_id: docId, note });
export const unlinkRuling = (linkId: number) => send<{ ok: boolean }>("DELETE", `/matter-rulings/${linkId}`);
export const rulingMatters = (docId: string) =>
  get<{ id: number; reference: string; title: string; linked: boolean }[]>(`/rulings/${encodeURIComponent(docId)}/matters`);

export const addTime = (matterId: number, b: { date?: string; minutes: number; description: string; rate: number }) =>
  send<TimeEntry>("POST", `/matters/${matterId}/time`, b);
export const addExpense = (matterId: number, b: { date?: string; label: string; amount: number }) =>
  send<Expense>("POST", `/matters/${matterId}/expenses`, b);
export const deleteTime = (id: number) => send<{ ok: boolean }>("DELETE", `/time/${id}`);
export const deleteExpense = (id: number) => send<{ ok: boolean }>("DELETE", `/expenses/${id}`);

export const feeNotes = (status = "") => get<FeeNote[]>(`/fees?${qs({ status })}`);
export const feeNote = (id: number) => get<FeeDetail>(`/fees/${id}`);
export const createFeeNote = (b: { matter_id?: number; client_id?: number; lines?: { label: string; amount: number }[];
  include_unbilled?: boolean; vat_rate?: number }) => send<FeeDetail>("POST", "/fees", b);
export const payFeeNote = (id: number, b: { amount: number; method: string; reference: string }) =>
  send<FeeDetail>("POST", `/fees/${id}/payments`, b);
export const cancelFeeNote = (id: number) => send<FeeDetail>("POST", `/fees/${id}/cancel`);
