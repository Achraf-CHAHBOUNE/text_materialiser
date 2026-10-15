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
  city: string; message: string; language: Lang; status: string; assigned_to: string;
  org_id: number | null; created_at: string;
};
export type Contact = {
  id: number; org_id: number; full_name: string; job_title: string; email: string; phone: string;
  language: Lang; is_primary: number;
};
export type Opportunity = {
  id: number; org_id: number; org_name?: string; title: string; stage: Stage; value: number;
  plan_code: string; expected_close: string | null; owner: string; lost_reason: string;
  closed_at: string | null; created_at: string;
};
export type Stage = "new" | "contacted" | "demo" | "trial" | "won" | "lost";
export const STAGES: Stage[] = ["new", "contacted", "demo", "trial", "won", "lost"];
export type ActivityRow = {
  id: number; org_id: number; kind: "call" | "email" | "meeting" | "note"; body: string; at: string; by_user: string;
};
export type TaskRow = {
  id: number; title: string; due_on: string; assigned_to: string; org_id: number | null;
  org_name?: string; done_at: string | null; created_by: string;
};
export type Health = "active" | "quiet" | "at_risk";
export type OrgRow = Org & {
  subscription: Subscription | null; access: Access; seats_used: number;
  activity_30d: number; health: Health;
};
export type OrgDetail = Org & {
  contacts: Contact[]; opportunities: Opportunity[]; activities: ActivityRow[]; tasks: TaskRow[];
  members: Person[]; invitations: Invitation[]; subscription: Subscription | null; access: Access;
  seats: { total: number; used: number }; activity_30d: number; health: Health;
  audit: { ts: string; actor: string; action: string; field: string; old: string; new: string }[];
};
export type Dashboard = {
  pipeline: { stage: Stage; count: number; value: number }[]; new_leads: number;
  revenue_month: number; outstanding: number; overdue_invoices: number;
  renewals: { org_id: number; name: string; ends_on: string; status: string; plan_code: string; days_left: number }[];
  at_risk: { id: number; name: string; activity_30d: number }[]; my_tasks_due: number; customers: number;
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

// ---------- CRM ----------
export const crmDashboard = () => j<Dashboard>("/api/crm/dashboard");
export const leads = (p: { status?: string; q?: string } = {}) => j<Lead[]>(`/api/crm/leads?${qs(p)}`);
export const createLead = (b: Partial<Lead>) => post<Lead>("/api/crm/leads", b);
export const updateLead = (id: number, b: Partial<Lead>) => patch<Lead>(`/api/crm/leads/${id}`, b);
export const convertLead = (id: number, b: { org_name?: string; kind?: string; trial?: boolean; invite?: boolean }) =>
  post<{ org: Org }>(`/api/crm/leads/${id}/convert`, b);
export const orgs = (p: { q?: string; status?: string } = {}) => j<OrgRow[]>(`/api/crm/orgs?${qs(p)}`);
export const createOrg = (b: Partial<Org>) => post<Org>("/api/crm/orgs", b);
export const orgDetail = (id: number) => j<OrgDetail>(`/api/crm/orgs/${id}`);
export const updateOrg = (id: number, b: Partial<Org>) => patch<Org>(`/api/crm/orgs/${id}`, b);
export const orgInvite = (id: number, email: string, role: Role, language: Lang) =>
  post<{ email: string }>(`/api/crm/orgs/${id}/invite`, { email, role, language });
export const createContact = (orgId: number, b: Partial<Contact>) => post<Contact>(`/api/crm/orgs/${orgId}/contacts`, b);
export const deleteContact = (id: number) => del<{ ok: boolean }>(`/api/crm/contacts/${id}`);
export const createOpp = (orgId: number, b: Partial<Opportunity>) =>
  post<Opportunity>(`/api/crm/orgs/${orgId}/opportunities`, b);
export const updateOpp = (id: number, b: Partial<Opportunity>) => patch<Opportunity>(`/api/crm/opportunities/${id}`, b);
export const pipeline = () => j<Opportunity[]>("/api/crm/pipeline");
export const addActivity = (orgId: number, b: { kind: string; body: string }) =>
  post<ActivityRow>(`/api/crm/orgs/${orgId}/activities`, b);
export const crmTasks = (p: { mine?: boolean; open_only?: boolean } = {}) => j<TaskRow[]>(`/api/crm/tasks?${qs(p)}`);
export const createTask = (b: { title: string; due_on: string; org_id?: number; assigned_to?: string }) =>
  post<TaskRow>("/api/crm/tasks", b);
export const updateTask = (id: number, b: { done?: boolean; due_on?: string; title?: string }) =>
  patch<TaskRow>(`/api/crm/tasks/${id}`, b);

// ---------- billing ----------
export const orgSubscriptions = (orgId: number) => j<Subscription[]>(`/api/crm/orgs/${orgId}/subscriptions`);
export const addSubscription = (orgId: number, b: { plan_code: string; status: string; days?: number | undefined; seats?: number | undefined }) =>
  post<{ id: number }>(`/api/crm/orgs/${orgId}/subscriptions`, b);
export const changeSubscription = (id: number, b: { status?: string; ends_on?: string; seats?: number }) =>
  patch<Subscription>(`/api/crm/subscriptions/${id}`, b);
export const orgInvoices = (orgId: number) => j<Invoice[]>(`/api/crm/orgs/${orgId}/invoices`);
export const addInvoice = (orgId: number, b: { amount_ht: number; description: string; vat_rate?: number; due_days?: number; send?: boolean }) =>
  post<Invoice>(`/api/crm/orgs/${orgId}/invoices`, b);
export const allInvoices = (status = "") => j<Invoice[]>(`/api/crm/invoices?${qs({ status })}`);
export const addPayment = (invoiceId: number, b: { amount: number; method: string; reference: string; paid_on?: string }) =>
  post<Invoice>(`/api/crm/invoices/${invoiceId}/payments`, b);
export const cancelInvoice = (invoiceId: number) => post<Invoice>(`/api/crm/invoices/${invoiceId}/cancel`);
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
