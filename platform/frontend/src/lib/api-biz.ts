// The business side of the API: accounts, CRM, billing, support, and a reader's library.
// Amounts are centimes (49900 = 499.00 MAD), as the server holds them.
import { request as j } from "./api";
import type { Lang } from "./lang-url";

const send = <T,>(method: string, path: string, body?: unknown) =>
  j<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
const post = <T,>(path: string, body?: unknown) => send<T>("POST", path, body);
const patch = <T,>(path: string, body?: unknown) => send<T>("PATCH", path, body);
const put = <T,>(path: string, body?: unknown) => send<T>("PUT", path, body);
const del = <T,>(path: string) => j<T>(path, { method: "DELETE" });
const qs = (o: Record<string, string | number | boolean | undefined>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => [k, String(v)])).toString();

// ---------- types ----------
export type Role = "admin" | "editor" | "sales" | "client_admin" | "client";
export type Person = {
  email: string; role: Role; status: "active" | "suspended"; full_name: string; phone: string;
  language: Lang; org_id: number | null; mfa: boolean; last_login: string; created_at?: string;
};
export type Org = {
  id: number; name: string; kind: string; city: string; ice: string; address: string; phone: string;
  email: string; language: Lang; account_manager: string; status: "prospect" | "customer" | "former";
  notes: string; created_at: string;
};
export type Plan = {
  code: string; name_ar: string; name_fr: string; blurb_ar: string; blurb_fr: string;
  price: number; period: "month" | "year" | "quote"; seats: number; daily_downloads: number;
  vat_rate: number; public: boolean; active: boolean; sort: number;
};
export type Subscription = {
  id: number; org_id: number; plan_code: string; plan_name_ar: string; plan_name_fr: string;
  seats: number; status: "trial" | "active" | "expired" | "suspended" | "cancelled";
  starts_on: string; ends_on: string; days_left: number; notes: string; created_by: string;
};
export type Access = "ok" | "none" | "expired" | "suspended";
export type Invoice = {
  id: number; number: string; org_id: number; org_name?: string; subscription_id: number | null;
  description: string; amount_ht: number; vat_rate: number; vat: number; amount_ttc: number;
  paid: number; balance: number; issued_on: string; due_on: string;
  status: "draft" | "sent" | "paid" | "overdue" | "cancelled"; created_by: string;
};
export type InvoiceDetail = Invoice & {
  org: Org | null;
  payments: { id: number; amount: number; method: string; reference: string; paid_on: string; recorded_by: string }[];
  seller: { name: string; address: string; ice: string; rib: string };
};
export type Account = {
  user: Person; org: Org | null; subscription: Subscription | null; access: Access;
  mfa_required: boolean; seats?: { total: number; used: number }; quota?: number;
};
export type Invitation = { id: number; email: string; role: Role; invited_by: string; expires_at: string };
export type Lead = {
  id: number; source: string; full_name: string; email: string; phone: string; company: string;
  city: string; message: string; language: Lang; status: "new" | "contacted" | "converted" | "rejected";
  org_id: number | null; created_at: string;
};
export type Health = "active" | "new" | "quiet" | "at_risk";
export type TransferRow = {
  id: number; org_id: number; contract_id: number | null; amount: number; paid_on: string; bank: string;
  bank_ref: string; has_proof: boolean; proof_name: string; invoice_id: number | null; recorded_by: string;
  created_at: string; org_name?: string; contract_number?: string;
};
export type ContractStatus = "awaiting_payment" | "upcoming" | "active" | "ended" | "cancelled" | "unassigned";
export type ContractRow = {
  id: number | null; number: string; org_id: number; org_name: string; plan_code: string;
  plan_name_ar: string; plan_name_fr: string; seats: number; starts_on: string; ends_on: string; days_left: number;
  amount_ht: number; vat_rate: number; vat: number; amount_ttc: number; received: number; balance: number;
  status: ContractStatus; notes: string; has_file: boolean; file_name: string; created_by: string; created_at: string;
  transfers: TransferRow[];
};
export type OrgRow = Org & {
  contract: ContractRow | null; access: Access; seats: { total: number; used: number };
  paid: number; owed: number; activity_30d: number; health: Health;
};
export type OrgDetail = Org & {
  members: Person[]; invitations: Invitation[]; subscription: Subscription | null; access: Access;
  seats: { total: number; used: number }; activity_30d: number; health: Health;
  contracts: ContractRow[]; paid: number; owed: number; invoices: Invoice[];
  audit: { ts: string; actor: string; action: string; field: string; old: string; new: string }[];
};
export type Ticket = {
  id: number; org_id: number | null; org_name: string; user_email: string; subject: string;
  status: "open" | "pending" | "closed"; priority: "normal" | "high"; assigned_to: string;
  created_at: string; updated_at: string;
  messages?: { id: number; author: string; staff: boolean; body: string; created_at: string }[];
};
export type Folder = { id: number; name: string; shared: boolean; owner: string; mine: boolean; count: number; created_at: string };
export type FolderDetail = Folder & {
  items: { id: number; doc_id: string; note: string; added_by: string; added_at: string;
    decision_no: string; date: string; chamber: string; theme: string; abstract: string; abstract_fr: string }[];
};
export type AlertRow = {
  id: number; name: string; query: string; chamber: string; theme: string; year: string; city: string;
  lang: Lang; frequency: "daily" | "weekly"; active: boolean; last_sent_at: string; created_at: string;
};
export type HistoryRow = {
  ts: string; action: "view" | "search" | "download"; query?: string;
  doc_id?: string; decision_no?: string; date?: string; chamber?: string;
};
export type Outbox = { id: number; to: string; template: string; lang: Lang; subject: string; body: string; status: string; error: string; created_at: string; sent_at: string };

// ---------- account ----------
export const getAccount = () => j<Account>("/api/account");
export const updateProfile = (b: Partial<Pick<Person, "full_name" | "phone" | "language">>) =>
  patch<Person>("/api/account/profile", b);
export const changePassword = (current: string, next: string) =>
  post<{ ok: boolean }>("/api/account/password", { current, new: next });
export const mfaSetup = () => post<{ secret: string; uri: string }>("/api/account/mfa/setup");
export const mfaEnable = (code: string) => post<{ ok: boolean }>("/api/account/mfa/enable", { code });
export const mfaDisable = (code: string) => post<{ ok: boolean }>("/api/account/mfa/disable", { code });
export const getTeam = () =>
  j<{ members: Person[]; invitations: Invitation[]; seats: { total: number; used: number } }>("/api/account/team");
export const inviteMember = (email: string, role: Role, language: Lang) =>
  post<{ email: string }>("/api/account/team/invite", { email, role, language });
export const cancelInvitation = (id: number) => del<{ ok: boolean }>(`/api/account/team/invitations/${id}`);
export const removeMember = (email: string) => del<{ ok: boolean }>(`/api/account/team/${encodeURIComponent(email)}`);
export const myInvoices = () => j<Invoice[]>("/api/account/invoices");
export const invitationInfo = (token: string) =>
  j<{ email: string; org: string; role: Role }>(`/api/invitations/${encodeURIComponent(token)}`);
export const acceptInvitation = (token: string, password: string, full_name: string) =>
  post<{ ok: boolean; email: string }>(`/api/invitations/${encodeURIComponent(token)}`, { password, full_name });
export const forgotPassword = (email: string, language: Lang) =>
  post<{ ok: boolean }>("/api/auth/forgot", { email, language });
export const resetPassword = (token: string, password: string) =>
  post<{ ok: boolean }>(`/api/auth/reset/${encodeURIComponent(token)}`, { password });

// ---------- public ----------
export const publicPlans = () => j<Plan[]>("/api/public/plans");
export const requestDemo = (b: { full_name: string; email: string; phone: string; company: string;
  city: string; message: string; language: Lang; website: string }) => post<{ ok: boolean }>("/api/public/demo", b);

// ---------- staff ----------
export const staffList = () => j<Person[]>("/api/admin/staff");
export const createStaff = (b: { email: string; role: Role; full_name: string; password: string }) =>
  post<{ email: string }>("/api/admin/staff", b);
export const updateUser = (email: string, b: { role?: Role; status?: "active" | "suspended" }) =>
  patch<Person>(`/api/admin/users/${encodeURIComponent(email)}`, b);
export const adminPlans = () => j<Plan[]>("/api/admin/plans");
export const savePlan = (p: Plan) => put<Plan>(`/api/admin/plans/${encodeURIComponent(p.code)}`, p);
export const outbox = () => j<Outbox[]>("/api/admin/outbox");

// ---------- CRM: clients, contracts, transfers ----------
export const leads = (status = "") => j<Lead[]>(`/api/crm/leads?${qs({ status })}`);
export const updateLead = (id: number, status: Lead["status"]) => patch<Lead>(`/api/crm/leads/${id}`, { status });
export const orgs = (q = "") => j<OrgRow[]>(`/api/crm/orgs?${qs({ q })}`);
export const orgDetail = (id: number) => j<OrgDetail>(`/api/crm/orgs/${id}`);
export const updateOrg = (id: number, b: Partial<Org>) => patch<Org>(`/api/crm/orgs/${id}`, b);
export const orgInvite = (id: number, email: string, role: Role, language: Lang) =>
  post<{ email: string }>(`/api/crm/orgs/${id}/invite`, { email, role, language });

export type NewClient = {
  org: { name: string; kind: string; ice: string; address: string; city: string; phone: string; email: string; language: Lang };
  contract: { plan_code: string; seats?: number | undefined; starts_on: string; ends_on: string; amount_ht: number; vat_rate: number; notes: string };
  transfer?: { amount: number; paid_on: string; bank: string; bank_ref: string } | undefined;
  accounts: { email: string; role: Role }[];
  lead_id?: number | undefined;
};
export const createClient = (b: NewClient) =>
  post<{ org_id: number; contract: { id: number; number: string }; transfer: TransferRow | null; invited: string[]; active: boolean }>("/api/crm/clients", b);
export const contracts = (status = "") => j<ContractRow[]>(`/api/crm/contracts?${qs({ status })}`);
export const transfers = () => j<TransferRow[]>("/api/crm/transfers");
export const addContract = (orgId: number, b: Partial<NewClient["contract"]>) =>
  post<{ id: number; number: string }>(`/api/crm/orgs/${orgId}/contracts`, b);
export const cancelContract = (id: number) => patch<ContractRow>(`/api/crm/contracts/${id}`, { cancel: true });
export const addTransfer = (contractId: number, b: { amount: number; paid_on?: string; bank?: string; bank_ref?: string }) =>
  post<TransferRow>(`/api/crm/contracts/${contractId}/transfers`, b);
export const invoiceFromTransfer = (id: number) => post<{ invoice_id: number; number?: string }>(`/api/crm/transfers/${id}/invoice`);
async function upload(path: string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return j<{ ok: boolean }>(path, { method: "POST", body: fd });
}
export const uploadContractFile = (id: number, file: File) => upload(`/api/crm/contracts/${id}/file`, file);
export const uploadProof = (id: number, file: File) => upload(`/api/crm/transfers/${id}/proof`, file);
/** Files behind the session: fetched with the token, then saved. */
export async function downloadWithSession(path: string, name: string) {
  const { apiBase, getToken } = await import("./api");
  const r = await fetch(`${apiBase}${path}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await r.blob());
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}
export const invoiceDetail = (invoiceId: number) => j<InvoiceDetail>(`/api/invoices/${invoiceId}`);

// ---------- support ----------
export const tickets = (status = "") => j<Ticket[]>(`/api/support?${qs({ status })}`);
export const openTicket = (b: { subject: string; body: string; priority?: string }) => post<Ticket>("/api/support", b);
export const ticket = (id: number) => j<Ticket>(`/api/support/${id}`);
export const replyTicket = (id: number, body: string) => post<Ticket>(`/api/support/${id}/reply`, { body });
export const updateTicket = (id: number, b: { status?: string; priority?: string; assigned_to?: string }) =>
  patch<Ticket>(`/api/support/${id}`, b);

// ---------- a reader's library ----------
export const folders = () => j<Folder[]>("/api/me/folders");
export const createFolder = (name: string, shared: boolean) => post<Folder>("/api/me/folders", { name, shared });
export const updateFolder = (id: number, name: string, shared: boolean) => patch<Folder>(`/api/me/folders/${id}`, { name, shared });
export const deleteFolder = (id: number) => del<{ ok: boolean }>(`/api/me/folders/${id}`);
export const folderDetail = (id: number, lang: Lang) => j<FolderDetail>(`/api/me/folders/${id}?lang=${lang}`);
export const addToFolder = (folderId: number, docId: string, note = "") =>
  post<{ ok: boolean; already?: boolean }>(`/api/me/folders/${folderId}/items`, { doc_id: docId, note });
export const setItemNote = (folderId: number, itemId: number, note: string) =>
  patch<{ ok: boolean }>(`/api/me/folders/${folderId}/items/${itemId}`, { note });
export const removeItem = (folderId: number, itemId: number) =>
  del<{ ok: boolean }>(`/api/me/folders/${folderId}/items/${itemId}`);
export const rulingFolders = (docId: string) => j<number[]>(`/api/me/rulings/${encodeURIComponent(docId)}/folders`);
export const alerts = () => j<AlertRow[]>("/api/me/alerts");
export const createAlert = (b: { name?: string; query?: string; chamber?: string; theme?: string;
  year?: string; city?: string; lang: Lang; frequency?: string }) => post<AlertRow>("/api/me/alerts", b);
export const updateAlert = (id: number, b: { active?: boolean; frequency?: string; name?: string }) =>
  patch<AlertRow>(`/api/me/alerts/${id}`, b);
export const deleteAlert = (id: number) => del<{ ok: boolean }>(`/api/me/alerts/${id}`);
export const history = () => j<HistoryRow[]>("/api/me/history");
export const myDownloads = () => j<{ used_today: number; quota: number | null }>("/api/me/downloads");

// ---------- the readers, as the admin sees them ----------
export type Counts = { view: number; download: number; search: number; search_empty: number; translate: number; login: number };
export type ReaderRow = {
  email: string; full_name: string; role: Role; status: "active" | "suspended"; org_id: number | null;
  org_name: string; plan: string; access: Access; ends_on: string; last_login: string; last_seen: string;
  reads_30d: number; downloads_30d: number; searches_30d: number; logins_30d: number; reads_total: number;
  org_paid: number; org_owed: number; sessions: number; reading_minutes_30d: number; french_share: number;
};
export type TimelineItem = { ts: string; action: string; query?: string; doc_id?: string; decision_no?: string; date?: string; chamber?: string };
export type ReaderDetail = {
  user: { email: string; full_name: string; phone: string; role: Role; status: "active" | "suspended";
    language: Lang; org_id: number | null; mfa: boolean; created_at: string; last_login: string };
  org: Org | null; subscription: Subscription | null; access: Access; quota: number; downloads_today: number;
  money: { paid: number; owed: number; invoices: Invoice[] };
  totals: Counts; recent: Counts; days: number;
  series: { day: string; view: number; download: number; search: number }[];
  chambers: { chamber: string; count: number }[];
  timeline: TimelineItem[];
  downloads: { ref: string; doc_id: string; at: string; decision_no?: string; chamber?: string; date?: string }[];
  sessions: { ip: string; device: string; created_at: string; last_seen: string; ended: string; why: string }[];
  audit: { ts: string; actor: string; action: string; field: string; old: string; new: string }[];
  reading: { minutes: number; french_share: number;
    longest: { doc_id: string; minutes: number; decision_no?: string; chamber?: string; date?: string }[] };
  contracts: ContractRow[];
  notes: { id: number; body: string; author: string; at: string }[];
};
type RulingCount = { doc_id: string; count: number; readers: number; decision_no?: string; chamber?: string; date?: string };
export type Usage = {
  days: number; readers: number; active_readers: number; totals: Counts;
  series: { day: string; users: number; view: number; download: number; search: number }[];
  top_read: RulingCount[]; top_downloaded: RulingCount[];
  top_searches: { query: string; count: number }[];
  empty_searches: { query: string; count: number; last: string }[];
  top_users: { email: string; view: number; download: number; search: number }[];
};
export const readers = (q = "") => j<ReaderRow[]>(`/api/crm/users?${qs({ q })}`);
export const readerDetail = (email: string, days = 30) =>
  j<ReaderDetail>(`/api/crm/users/${encodeURIComponent(email)}?days=${days}`);
export const forceLogout = (email: string) => post<{ ended: number }>(`/api/crm/users/${encodeURIComponent(email)}/logout`);
export const usage = (days = 30) => j<Usage>(`/api/crm/usage?days=${days}`);
export async function exportActivity(days: number, email = "") {
  const { apiBase, getToken } = await import("./api");
  const r = await fetch(`${apiBase}/api/crm/activity/export?${qs({ days, email })}`,
                        { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await r.blob());
  a.download = `activite-${email || "tous"}-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

// ---------- following the readers: alerts, a file's trail, notes, the first screen ----------
export type AlertItem = {
  kind: "shared_ips" | "many_devices" | "quota_hit" | "too_fast" | "inactive" | "awaiting_payment" | "ending" | "balance";
  level: "high" | "medium" | "low"; email?: string; org_id?: number; org?: string; count: number; at: string; detail: string;
};
export type Overview = {
  readers: number; clients_open: number; active_today: number; active_7d: number; active_30d: number; new_readers_30d: number;
  received_month: number; received_year: number; owed: number; contracts_active: number; contracts_ending: number;
  awaiting_payment: number; alerts_high: number; alerts: number; new_requests: number; usage: Usage;
};
export type FoundDownload = { ref: string; email: string; org_id: number | null; org: string; doc_id: string; at: string;
  decision_no?: string; chamber?: string; date?: string };
export const crmAlerts = () => j<AlertItem[]>("/api/crm/alerts");
export const overview = () => j<Overview>("/api/crm/overview");
export const moneyTotals = () => j<{ received_month: number; received_year: number; owed: number }>("/api/crm/money");
export const findDownload = (ref: string) => j<FoundDownload>(`/api/crm/downloads/${encodeURIComponent(ref.trim())}`);
export const addNote = (email: string, body: string) =>
  post<{ id: number }>(`/api/crm/users/${encodeURIComponent(email)}/notes`, { body });
export const emailReader = (email: string, subject: string, body: string) =>
  post<{ ok: boolean }>(`/api/crm/users/${encodeURIComponent(email)}/email`, { subject, body });
