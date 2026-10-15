import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Ban, CheckCircle2, Mail, Phone, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, Select, Stat, STATUS_TONE, Table, Td, TextField, when } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { InvoiceTable } from "@/components/InvoiceTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  addActivity, addInvoice, addPayment, addSubscription, adminPlans, cancelInvoice, changeSubscription,
  createContact, createOpp, createTask, deleteContact, orgDetail, orgInvite, orgInvoices, orgSubscriptions,
  STAGES, updateOpp, updateOrg, updateTask, updateUser, type Invoice, type Org, type OrgDetail, type Role, type Stage,
} from "@/lib/api-biz";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/orgs/$orgId")({
  component: OrgPage,
});

const fail = (fallback: string) => (e: unknown) => toast.error(e instanceof Error ? e.message : fallback);

function OrgPage() {
  const { orgId } = Route.useParams();
  const id = Number(orgId);
  const { t, lang, num, status } = useI18n();
  const q = useQuery({ queryKey: ["org", id], queryFn: () => orgDetail(id) });
  const o = q.data;
  return (
    <AppShell title={o?.name ?? t("crm.org")} description={o ? `${t(`kind.${o.kind}` as "kind.firm")}${o.city ? ` · ${o.city}` : ""}` : ""}
              action={o && <Badge tone={STATUS_TONE[o.status]}>{status(o.status)}</Badge>}>
      <CrmNav />
      {o && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label={t("acc.subscription")}
                  value={o.subscription ? (lang === "fr" ? o.subscription.plan_name_fr : o.subscription.plan_name_ar) : "—"}
                  hint={o.subscription && <Badge tone={STATUS_TONE[o.access === "ok" ? o.subscription.status : o.access]}>{status(o.access === "ok" ? o.subscription.status : o.access)}</Badge>} />
            <Stat label={t("acc.until")} value={o.subscription ? day(o.subscription.ends_on) : "—"}
                  tone={o.subscription && o.subscription.days_left < 30 ? "warn" : "default"} />
            <Stat label={t("pub.seats")} value={`${num(o.seats.used)} / ${num(o.seats.total)}`} />
            <Stat label={t("crm.health")} value={status(o.health)} hint={`${num(o.activity_30d)} ${t("crm.actions30")}`}
                  tone={o.health === "at_risk" ? "bad" : o.health === "quiet" ? "warn" : "good"} />
          </div>
          <Tabs defaultValue="overview" className="mt-4">
            <TabsList className="flex-wrap">
              <TabsTrigger value="overview">{t("crm.tabOverview")}</TabsTrigger>
              <TabsTrigger value="people">{t("crm.tabPeople")}</TabsTrigger>
              <TabsTrigger value="subscription">{t("acc.subscription")}</TabsTrigger>
              <TabsTrigger value="invoices">{t("bill.invoices")}</TabsTrigger>
              <TabsTrigger value="activity">{t("crm.tabActivity")}</TabsTrigger>
              <TabsTrigger value="history">{t("crm.tabHistory")}</TabsTrigger>
            </TabsList>
            <TabsContent value="overview" className="mt-4"><Overview o={o} /></TabsContent>
            <TabsContent value="people" className="mt-4"><People o={o} /></TabsContent>
            <TabsContent value="subscription" className="mt-4"><Subscriptions orgId={id} /></TabsContent>
            <TabsContent value="invoices" className="mt-4"><Invoices orgId={id} /></TabsContent>
            <TabsContent value="activity" className="mt-4"><ActivityTab o={o} /></TabsContent>
            <TabsContent value="history" className="mt-4">
              <Card>
                {o.audit.length === 0 ? <Empty>{t("history.empty")}</Empty> : (
                  <ul className="divide-y text-sm">
                    {o.audit.map((a, i) => (
                      <li key={i} className="py-2"><span className="text-xs text-muted-foreground">{when(a.ts)} · {a.actor}</span>
                        <p>{a.action}{a.field ? ` · ${a.field}` : ""}{a.new ? ` → ${a.new}` : ""}</p></li>
                    ))}
                  </ul>
                )}
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
    </AppShell>
  );
}

function useRefresh(id: number) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["org", id] });
    void qc.invalidateQueries({ queryKey: ["org-subs", id] });
    void qc.invalidateQueries({ queryKey: ["org-invoices", id] });
  };
}

function Overview({ o }: { o: OrgDetail }) {
  const { t } = useI18n();
  const refresh = useRefresh(o.id);
  const [f, setF] = useState<Partial<Org>>({ name: o.name, kind: o.kind, city: o.city, ice: o.ice, address: o.address,
    phone: o.phone, email: o.email, language: o.language, account_manager: o.account_manager, status: o.status, notes: o.notes });
  const set = (k: keyof Org) => (v: string) => setF({ ...f, [k]: v });
  const save = useMutation({ mutationFn: () => updateOrg(o.id, f), onSuccess: () => { toast.success(t("adm.saved")); refresh(); }, onError: fail(t("adm.failed")) });
  return (
    <Card>
      <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextField label={t("crm.orgName")} value={f.name ?? ""} onChange={set("name")} required />
        <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("crm.kind")}</p>
          <Select value={f.kind ?? "firm"} onChange={set("kind")} className="w-full"
                  options={["firm", "company", "institution", "individual"].map((k) => ({ value: k, label: t(`kind.${k}` as "kind.firm") }))} /></div>
        <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("adm.colStatus")}</p>
          <Select value={f.status ?? "prospect"} onChange={set("status")} className="w-full"
                  options={["prospect", "customer", "former"].map((k) => ({ value: k, label: t(`st.${k}` as "st.customer") }))} /></div>
        <TextField label={t("col.city")} value={f.city ?? ""} onChange={set("city")} />
        <TextField label={t("crm.address")} value={f.address ?? ""} onChange={set("address")} />
        <TextField label="ICE" value={f.ice ?? ""} onChange={set("ice")} dir="ltr" />
        <TextField label={t("adm.colEmail")} value={f.email ?? ""} onChange={set("email")} dir="ltr" />
        <TextField label={t("pub.phone")} value={f.phone ?? ""} onChange={set("phone")} dir="ltr" />
        <TextField label={t("crm.manager")} value={f.account_manager ?? ""} onChange={set("account_manager")} dir="ltr" />
        <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("acc.emailLanguage")}</p>
          <Select value={f.language ?? "ar"} onChange={set("language")} className="w-full"
                  options={[{ value: "ar", label: "العربية" }, { value: "fr", label: "Français" }]} /></div>
        <div className="sm:col-span-2 lg:col-span-3">
          <Textarea value={f.notes ?? ""} onChange={(e) => set("notes")(e.target.value)} rows={3} placeholder={t("crm.notes")} aria-label={t("crm.notes")} />
        </div>
        <Button type="submit" size="sm" className="w-fit" disabled={save.isPending}>{t("adm.save")}</Button>
      </form>
    </Card>
  );
}

function People({ o }: { o: OrgDetail }) {
  const { t, lang, status } = useI18n();
  const { isSuper } = useStore();
  const refresh = useRefresh(o.id);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("client");
  const [c, setC] = useState({ full_name: "", job_title: "", email: "", phone: "" });
  const invite = useMutation({ mutationFn: () => orgInvite(o.id, email, role, o.language || lang),
    onSuccess: () => { toast.success(t("team.invited")); setEmail(""); refresh(); }, onError: fail(t("adm.failed")) });
  const addContact = useMutation({ mutationFn: () => createContact(o.id, c),
    onSuccess: () => { setC({ full_name: "", job_title: "", email: "", phone: "" }); refresh(); }, onError: fail(t("adm.failed")) });
  const dropContact = useMutation({ mutationFn: deleteContact, onSuccess: refresh });
  const changeUser = useMutation({ mutationFn: (x: { email: string; role?: Role; status?: "active" | "suspended" }) => updateUser(x.email, x),
    onSuccess: refresh, onError: fail(t("adm.failed")) });
  return (
    <div className="grid gap-4">
      <Card title={t("crm.accounts")}>
        <form className="mb-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}>
          <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="avocat@cabinet.ma"
                 className="h-10 max-w-xs" dir="ltr" aria-label={t("adm.colEmail")} />
          <Select value={role} onChange={(v) => setRole(v as Role)} label={t("settings.role")}
                  options={[{ value: "client", label: t("role.client") }, { value: "client_admin", label: t("role.client_admin") }]} />
          <Button type="submit" disabled={invite.isPending}>{t("team.invite")}</Button>
        </form>
        <Table head={[t("pub.name"), t("adm.colEmail"), t("settings.role"), t("adm.colStatus"), t("adm.colLastLogin"), ""]}>
          {o.members.map((m) => (
            <tr key={m.email}>
              <Td>{m.full_name || "—"}</Td><Td><span dir="ltr">{m.email}</span></Td>
              <Td>
                <Select value={m.role} onChange={(v) => changeUser.mutate({ email: m.email, role: v as Role })} className="h-8 text-xs" label={t("settings.role")}
                        options={[{ value: "client", label: t("role.client") }, { value: "client_admin", label: t("role.client_admin") }]} />
              </Td>
              <Td><Badge tone={STATUS_TONE[m.status]}>{status(m.status)}</Badge></Td>
              <Td className="text-xs">{day(m.last_login)}</Td>
              <Td>
                <Button size="sm" variant="ghost" aria-label={m.status === "active" ? t("adm.suspend") : t("adm.activate")}
                        onClick={() => changeUser.mutate({ email: m.email, status: m.status === "active" ? "suspended" : "active" })}>
                  {m.status === "active" ? <Ban className="size-4" /> : <CheckCircle2 className="size-4" />}
                </Button>
              </Td>
            </tr>
          ))}
          {o.invitations.map((i) => (
            <tr key={`i${i.id}`} className="text-muted-foreground">
              <Td>—</Td><Td><span dir="ltr">{i.email}</span></Td><Td>{t(`role.${i.role}` as "role.client")}</Td>
              <Td><Badge tone="info">{t("team.pending")}</Badge></Td><Td className="text-xs">{t("team.until")} {day(i.expires_at)}</Td><Td />
            </tr>
          ))}
        </Table>
        {!isSuper && <p className="mt-2 text-xs text-muted-foreground">{t("crm.staffOnlyAdmin")}</p>}
      </Card>
      <Card title={t("crm.contacts")}>
        <form className="mb-3 grid gap-2 sm:grid-cols-5" onSubmit={(e) => { e.preventDefault(); addContact.mutate(); }}>
          <Input required value={c.full_name} onChange={(e) => setC({ ...c, full_name: e.target.value })} placeholder={t("pub.name")} className="h-10" aria-label={t("pub.name")} />
          <Input value={c.job_title} onChange={(e) => setC({ ...c, job_title: e.target.value })} placeholder={t("crm.jobTitle")} className="h-10" aria-label={t("crm.jobTitle")} />
          <Input value={c.email} onChange={(e) => setC({ ...c, email: e.target.value })} placeholder={t("adm.colEmail")} className="h-10" dir="ltr" aria-label={t("adm.colEmail")} />
          <Input value={c.phone} onChange={(e) => setC({ ...c, phone: e.target.value })} placeholder={t("pub.phone")} className="h-10" dir="ltr" aria-label={t("pub.phone")} />
          <Button type="submit"><Plus className="size-4" />{t("adm.create")}</Button>
        </form>
        {o.contacts.length === 0 ? <Empty>{t("crm.noContacts")}</Empty> : (
          <ul className="divide-y text-sm">
            {o.contacts.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span><b>{x.full_name}</b>{x.job_title && <span className="text-muted-foreground"> · {x.job_title}</span>}
                  {x.is_primary ? <Badge tone="info">{t("crm.primary")}</Badge> : null}</span>
                <span className="flex items-center gap-3 text-xs text-muted-foreground">
                  {x.email && <a href={`mailto:${x.email}`} className="flex items-center gap-1 hover:text-foreground" dir="ltr"><Mail className="size-3" />{x.email}</a>}
                  {x.phone && <a href={`tel:${x.phone}`} className="flex items-center gap-1 hover:text-foreground" dir="ltr"><Phone className="size-3" />{x.phone}</a>}
                  <Button size="sm" variant="ghost" onClick={() => dropContact.mutate(x.id)} aria-label={t("lib.delete")}><Trash2 className="size-3.5" /></Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Subscriptions({ orgId }: { orgId: number }) {
  const { t, lang, num, status } = useI18n();
  const refresh = useRefresh(orgId);
  const subs = useQuery({ queryKey: ["org-subs", orgId], queryFn: () => orgSubscriptions(orgId) });
  const plans = useQuery({ queryKey: ["admin-plans"], queryFn: adminPlans });
  const [plan, setPlan] = useState("firm");
  const [kind, setKind] = useState("active");
  const [days, setDays] = useState("365");
  const [seats, setSeats] = useState("");
  const add = useMutation({
    mutationFn: () => addSubscription(orgId, { plan_code: plan, status: kind, days: Number(days) || undefined, seats: Number(seats) || undefined }),
    onSuccess: () => { toast.success(t("adm.saved")); refresh(); }, onError: fail(t("adm.failed")),
  });
  const change = useMutation({ mutationFn: (x: { id: number; status?: string }) => changeSubscription(x.id, x), onSuccess: refresh });
  return (
    <div className="grid gap-4">
      <Card title={t("crm.newSubscription")}>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Select value={plan} onChange={setPlan} label={t("crm.plan")}
                  options={(plans.data ?? []).map((p) => ({ value: p.code, label: lang === "fr" ? p.name_fr : p.name_ar }))} />
          <Select value={kind} onChange={setKind} label={t("adm.colStatus")}
                  options={[{ value: "active", label: status("active") }, { value: "trial", label: status("trial") }]} />
          <Input value={days} onChange={(e) => setDays(e.target.value)} className="h-10 w-24" inputMode="numeric" aria-label={t("crm.days")} />
          <span className="pb-2 text-sm text-muted-foreground">{t("crm.days")}</span>
          <Input value={seats} onChange={(e) => setSeats(e.target.value)} className="h-10 w-24" inputMode="numeric" placeholder={t("pub.seats")} aria-label={t("pub.seats")} />
          <Button type="submit" disabled={add.isPending}>{t("adm.create")}</Button>
        </form>
        <p className="mt-2 text-xs text-muted-foreground">{t("crm.renewHint")}</p>
      </Card>
      <Card title={t("crm.subscriptions")}>
        {(subs.data ?? []).length === 0 ? <Empty>{t("acc.noSubscription")}</Empty> : (
          <Table head={[t("crm.plan"), t("adm.colStatus"), t("crm.from"), t("acc.until"), t("pub.seats"), ""]}>
            {(subs.data ?? []).map((s) => (
              <tr key={s.id}>
                <Td>{lang === "fr" ? s.plan_name_fr : s.plan_name_ar}</Td>
                <Td><Badge tone={STATUS_TONE[s.status]}>{status(s.status)}</Badge></Td>
                <Td>{day(s.starts_on)}</Td><Td>{day(s.ends_on)}</Td><Td>{num(s.seats)}</Td>
                <Td>
                  {(s.status === "active" || s.status === "trial") && (
                    <Button size="sm" variant="ghost" onClick={() => change.mutate({ id: s.id, status: "suspended" })}>{t("adm.suspend")}</Button>
                  )}
                  {s.status === "suspended" && (
                    <Button size="sm" variant="ghost" onClick={() => change.mutate({ id: s.id, status: "active" })}>{t("adm.activate")}</Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

function Invoices({ orgId }: { orgId: number }) {
  const { t, lang } = useI18n();
  const refresh = useRefresh(orgId);
  const list = useQuery({ queryKey: ["org-invoices", orgId], queryFn: () => orgInvoices(orgId) });
  const [amount, setAmount] = useState("");
  const [desc, setDesc] = useState("");
  const add = useMutation({
    mutationFn: () => addInvoice(orgId, { amount_ht: Math.round(parseFloat(amount.replace(",", ".")) * 100), description: desc }),
    onSuccess: () => { toast.success(t("bill.created")); setAmount(""); setDesc(""); refresh(); }, onError: fail(t("adm.failed")),
  });
  return (
    <div className="grid gap-4">
      <Card title={t("bill.new")}>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Input required value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={t("bill.description")} className="h-10 max-w-sm" aria-label={t("bill.description")} />
          <Input required value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={`${t("bill.amountHt")} (MAD)`} inputMode="decimal" className="h-10 w-44" dir="ltr" aria-label={t("bill.amountHt")} />
          <Button type="submit" disabled={add.isPending}>{t("adm.create")}</Button>
        </form>
        <p className="mt-2 text-xs text-muted-foreground">{t("bill.newHint")}</p>
      </Card>
      <Card title={t("bill.invoices")}>
        <InvoiceTable rows={list.data ?? []} onChange={refresh} lang={lang} />
      </Card>
    </div>
  );
}

function ActivityTab({ o }: { o: OrgDetail }) {
  const { t, lang, status } = useI18n();
  const refresh = useRefresh(o.id);
  const [kind, setKind] = useState("call");
  const [body, setBody] = useState("");
  const [task, setTask] = useState("");
  const [due, setDue] = useState(new Date(Date.now() + 86400000).toISOString().slice(0, 10));
  const [oppTitle, setOppTitle] = useState("");
  const log = useMutation({ mutationFn: () => addActivity(o.id, { kind, body }), onSuccess: () => { setBody(""); refresh(); }, onError: fail(t("adm.failed")) });
  const addTask = useMutation({ mutationFn: () => createTask({ title: task, due_on: due, org_id: o.id }), onSuccess: () => { setTask(""); refresh(); }, onError: fail(t("adm.failed")) });
  const done = useMutation({ mutationFn: (x: { id: number; done: boolean }) => updateTask(x.id, { done: x.done }), onSuccess: refresh });
  const addOpp = useMutation({ mutationFn: () => createOpp(o.id, { title: oppTitle || o.name, stage: "new" }), onSuccess: () => { setOppTitle(""); refresh(); } });
  const moveOpp = useMutation({ mutationFn: (x: { id: number; stage: Stage; value?: number }) => updateOpp(x.id, x), onSuccess: refresh });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title={t("crm.opportunities")} className="lg:col-span-2">
        <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); addOpp.mutate(); }}>
          <Input value={oppTitle} onChange={(e) => setOppTitle(e.target.value)} placeholder={t("crm.oppTitle")} className="h-10 max-w-sm" aria-label={t("crm.oppTitle")} />
          <Button type="submit" variant="outline"><Plus className="size-4" />{t("crm.newOpp")}</Button>
        </form>
        {o.opportunities.length === 0 ? <Empty>{t("crm.noOpps")}</Empty> : (
          <Table head={[t("crm.oppTitle"), t("crm.stage"), t("crm.value"), t("crm.owner")]}>
            {o.opportunities.map((x) => (
              <tr key={x.id}>
                <Td>{x.title}</Td>
                <Td><Select value={x.stage} onChange={(s) => moveOpp.mutate({ id: x.id, stage: s as Stage })} className="h-8 text-xs" label={t("crm.stage")}
                            options={STAGES.map((s) => ({ value: s, label: status(s) }))} /></Td>
                <Td>
                  <Input defaultValue={x.value ? String(x.value / 100) : ""} className="h-8 w-28" dir="ltr" inputMode="decimal" aria-label={t("crm.value")}
                         onBlur={(e) => { const v = Math.round(parseFloat(e.target.value.replace(",", ".") || "0") * 100); if (v !== x.value) moveOpp.mutate({ id: x.id, stage: x.stage, value: v }); }} />
                  <span className="text-xs text-muted-foreground"> {money(x.value, lang)}</span>
                </Td>
                <Td className="text-xs">{x.owner}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title={t("crm.logActivity")}>
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); log.mutate(); }}>
          <Select value={kind} onChange={setKind} label={t("crm.activityKind")}
                  options={["call", "email", "meeting", "note"].map((k) => ({ value: k, label: t(`act.${k}` as "act.call") }))} />
          <Textarea required value={body} onChange={(e) => setBody(e.target.value)} rows={3} aria-label={t("crm.notes")} />
          <Button type="submit" size="sm" disabled={log.isPending}>{t("adm.save")}</Button>
        </form>
        <ul className="mt-4 divide-y text-sm">
          {o.activities.map((a) => (
            <li key={a.id} className="py-2"><p className="text-xs text-muted-foreground">{t(`act.${a.kind}` as "act.call")} · {when(a.at)} · {a.by_user}</p>
              <p className="whitespace-pre-wrap">{a.body}</p></li>
          ))}
        </ul>
      </Card>
      <Card title={t("crm.tasks")}>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); addTask.mutate(); }}>
          <Input required value={task} onChange={(e) => setTask(e.target.value)} placeholder={t("crm.taskTitle")} className="h-10 flex-1" aria-label={t("crm.taskTitle")} />
          <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="h-10 w-40" aria-label={t("bill.due")} />
          <Button type="submit" size="sm" className="h-10">{t("adm.create")}</Button>
        </form>
        <ul className="mt-3 divide-y text-sm">
          {o.tasks.map((x) => (
            <li key={x.id} className="flex items-center gap-2 py-2">
              <input type="checkbox" checked={!!x.done_at} onChange={(e) => done.mutate({ id: x.id, done: e.target.checked })} aria-label={x.title} />
              <span className={x.done_at ? "text-muted-foreground line-through" : ""}>{x.title}</span>
              <span className="ms-auto text-xs text-muted-foreground">{day(x.due_on)} · {x.assigned_to}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
