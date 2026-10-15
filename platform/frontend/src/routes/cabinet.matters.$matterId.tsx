import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { CalendarPlus, Download, FileText, Paperclip, Receipt, ShieldAlert, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, Select, Stat, STATUS_TONE, Table, Td, TextField, when } from "@/components/biz";
import { CabinetNav } from "@/components/cabinet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  addDeadline, addExpense, addHearing, addTask, addTime, createFeeNote, deadlinePresets, deleteDocument,
  deleteExpense, deleteHearing, deleteTime, downloadDocument, eraseMatter, firmMembers, matter, pClients,
  unlinkRuling, updateDeadline, updateHearing, updateMatter, updateTask, uploadDocument,
  type Matter, type MatterDetail,
} from "@/lib/api-practice";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/cabinet/matters/$matterId")({
  component: MatterPage,
});

const fail = (fallback: string) => (e: unknown) => toast.error(e instanceof Error ? e.message : fallback);
const today = () => new Date().toISOString().slice(0, 10);
const cents = (v: string) => Math.round(parseFloat((v || "0").replace(",", ".")) * 100);

function MatterPage() {
  const { matterId } = Route.useParams();
  const id = Number(matterId);
  const { t, lang, level, num } = useI18n();
  const { isClientAdmin } = useStore();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["matter", id, lang], queryFn: () => matter(id, lang) });
  const erase = useMutation({
    mutationFn: () => eraseMatter(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["matters"] }); navigate({ to: "/cabinet/matters" }); },
    onError: fail(t("adm.failed")),
  });
  const m = q.data;
  const nextHearing = m?.hearings.filter((h) => h.date >= today()).sort((a, b) => a.date.localeCompare(b.date))[0];
  const nextDeadline = m?.deadlines.filter((d) => !d.done_at).sort((a, b) => a.due_on.localeCompare(b.due_on))[0];
  return (
    <AppShell title={m ? m.title : t("cab.matter")}
              description={m ? `${m.reference}${m.client ? ` · ${m.client.full_name}` : ""}${m.court ? ` · ${m.court}` : ""}${m.level ? ` · ${level(m.level)}` : ""}` : ""}
              action={m && isClientAdmin && (
                <Button size="sm" variant="ghost" className="text-destructive" aria-label={t("cab.erase")}
                        onClick={() => { if (window.confirm(t("cab.eraseMatterConfirm"))) erase.mutate(); }}>
                  <Trash2 className="size-4" />
                </Button>
              )}>
      <CabinetNav />
      {m && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label={t("cab.nextHearing")} value={nextHearing ? day(nextHearing.date) : "—"} hint={nextHearing?.time} />
            <Stat label={t("cab.nextDeadline")} value={nextDeadline ? day(nextDeadline.due_on) : "—"}
                  tone={nextDeadline && nextDeadline.due_on < today() ? "bad" : nextDeadline ? "warn" : "default"}
                  hint={nextDeadline && !nextDeadline.verified_by ? t("cab.toVerify") : undefined} />
            <Stat label={t("cab.documents")} value={num(m.documents.length)} />
            <Stat label={t("cab.unbilled")} value={money(m.unbilled, lang)} />
          </div>
          <Tabs defaultValue="info" className="mt-4">
            <TabsList className="flex-wrap">
              <TabsTrigger value="info">{t("crm.tabOverview")}</TabsTrigger>
              <TabsTrigger value="hearings">{t("cab.hearings")} ({num(m.hearings.length)})</TabsTrigger>
              <TabsTrigger value="deadlines">{t("cab.deadlinesTasks")}</TabsTrigger>
              <TabsTrigger value="docs">{t("cab.documents")} ({num(m.documents.length)})</TabsTrigger>
              <TabsTrigger value="money">{t("cab.feesTab")}</TabsTrigger>
              <TabsTrigger value="law">{t("cab.caseLaw")} ({num(m.rulings.length)})</TabsTrigger>
            </TabsList>
            <TabsContent value="info" className="mt-4"><Info key={m.id} m={m} /></TabsContent>
            <TabsContent value="hearings" className="mt-4"><Hearings m={m} /></TabsContent>
            <TabsContent value="deadlines" className="mt-4"><DeadlinesTasks m={m} /></TabsContent>
            <TabsContent value="docs" className="mt-4"><Documents m={m} /></TabsContent>
            <TabsContent value="money" className="mt-4"><Money m={m} /></TabsContent>
            <TabsContent value="law" className="mt-4"><CaseLaw m={m} /></TabsContent>
          </Tabs>
        </>
      )}
    </AppShell>
  );
}

function useRefresh(id: number) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["matter", id] });
    void qc.invalidateQueries({ queryKey: ["firm-dashboard"] });
    void qc.invalidateQueries({ queryKey: ["firm-agenda"] });
  };
}

function Info({ m }: { m: MatterDetail }) {
  const { t, level } = useI18n();
  const refresh = useRefresh(m.id);
  const clients = useQuery({ queryKey: ["p-clients", ""], queryFn: () => pClients("") });
  const members = useQuery({ queryKey: ["firm-members"], queryFn: firmMembers });
  const [f, setF] = useState<Partial<Matter>>({
    title: m.title, client_id: m.client_id, client_role: m.client_role, opposing_party: m.opposing_party,
    opposing_lawyer: m.opposing_lawyer, court: m.court, chamber: m.chamber, city: m.city, level: m.level,
    case_number: m.case_number, kind: m.kind, status: m.status, responsible: m.responsible,
    fee_agreement: m.fee_agreement, notes: m.notes });
  const set = (k: keyof Matter) => (v: string) => setF({ ...f, [k]: v });
  const save = useMutation({ mutationFn: () => updateMatter(m.id, f), onSuccess: () => { toast.success(t("adm.saved")); refresh(); }, onError: fail(t("adm.failed")) });
  const sel = (label: string, value: string, onChange: (v: string) => void, options: { value: string; label: string }[]) => (
    <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{label}</p>
      <Select value={value} onChange={onChange} className="w-full" options={options} /></div>
  );
  return (
    <Card>
      <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="sm:col-span-2 lg:col-span-3"><TextField label={t("cab.matterTitle")} value={f.title ?? ""} onChange={set("title")} required /></div>
        {sel(t("cab.client"), String(f.client_id ?? ""), (v) => setF({ ...f, client_id: v ? Number(v) : null }),
          [{ value: "", label: "—" }, ...(clients.data ?? []).map((c) => ({ value: String(c.id), label: c.full_name }))])}
        {sel(t("cab.clientRole"), f.client_role ?? "", set("client_role"),
          [{ value: "", label: "—" }, ...["plaintiff", "defendant", "appellant", "respondent", "other"].map((r) => ({ value: r, label: t(`cab.role.${r}` as "cab.role.plaintiff") }))])}
        <TextField label={t("cab.opposing")} value={f.opposing_party ?? ""} onChange={set("opposing_party")} />
        <TextField label={t("cab.opposingLawyer")} value={f.opposing_lawyer ?? ""} onChange={set("opposing_lawyer")} />
        <TextField label={t("cab.court")} value={f.court ?? ""} onChange={set("court")} />
        <TextField label={t("col.chamber")} value={f.chamber ?? ""} onChange={set("chamber")} />
        <TextField label={t("col.city")} value={f.city ?? ""} onChange={set("city")} />
        {sel(t("col.level"), f.level ?? "", (v) => setF({ ...f, level: v as Matter["level"] }),
          [{ value: "", label: "—" }, ...["ابتدائي", "استئناف", "نقض"].map((l) => ({ value: l, label: level(l) }))])}
        <TextField label={t("col.fileNo")} value={f.case_number ?? ""} onChange={set("case_number")} dir="ltr" />
        <TextField label={t("cab.kindOfCase")} value={f.kind ?? ""} onChange={set("kind")} />
        {sel(t("cab.responsible"), f.responsible ?? "", set("responsible"),
          (members.data ?? []).map((x) => ({ value: x.email, label: x.full_name || x.email })))}
        {sel(t("adm.colStatus"), f.status ?? "open", set("status"),
          ["open", "closed", "archived"].map((s) => ({ value: s, label: t(`cab.status.${s}` as "cab.status.open") })))}
        <div className="sm:col-span-2 lg:col-span-3 grid gap-3 lg:grid-cols-2">
          <Textarea value={f.fee_agreement ?? ""} onChange={(e) => set("fee_agreement")(e.target.value)} rows={3} placeholder={t("cab.feeAgreement")} aria-label={t("cab.feeAgreement")} />
          <Textarea value={f.notes ?? ""} onChange={(e) => set("notes")(e.target.value)} rows={3} placeholder={t("crm.notes")} aria-label={t("crm.notes")} />
        </div>
        <Button type="submit" size="sm" className="w-fit" disabled={save.isPending}>{t("adm.save")}</Button>
      </form>
    </Card>
  );
}

function Hearings({ m }: { m: MatterDetail }) {
  const { t } = useI18n();
  const refresh = useRefresh(m.id);
  const [f, setF] = useState({ date: "", time: "", room: "", purpose: "" });
  const add = useMutation({ mutationFn: () => addHearing(m.id, f), onSuccess: () => { setF({ date: "", time: "", room: "", purpose: "" }); refresh(); }, onError: fail(t("adm.failed")) });
  const drop = useMutation({ mutationFn: deleteHearing, onSuccess: refresh });
  return (
    <div className="grid gap-4">
      <Card title={<span className="flex items-center gap-2"><CalendarPlus className="size-4 text-teal" />{t("cab.addHearing")}</span>}>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Input type="date" required value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} className="h-10 w-40" aria-label={t("col.date")} />
          <Input type="time" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} className="h-10 w-28" aria-label={t("cab.time")} />
          <Input value={f.room} onChange={(e) => setF({ ...f, room: e.target.value })} placeholder={t("cab.room")} className="h-10 w-32" aria-label={t("cab.room")} />
          <Input value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} placeholder={t("cab.purpose")} className="h-10 flex-1" aria-label={t("cab.purpose")} />
          <Button type="submit" disabled={add.isPending}>{t("adm.create")}</Button>
        </form>
      </Card>
      <Card title={t("cab.hearings")}>
        {m.hearings.length === 0 ? <Empty>{t("cab.noHearings")}</Empty> : (
          <ul className="space-y-3">
            {m.hearings.map((h) => <HearingRow key={h.id} h={h} onChange={refresh} onDelete={() => drop.mutate(h.id)} />)}
          </ul>
        )}
      </Card>
    </div>
  );
}

function HearingRow({ h, onChange, onDelete }: { h: MatterDetail["hearings"][number]; onChange: () => void; onDelete: () => void }) {
  const { t } = useI18n();
  const [outcome, setOutcome] = useState(h.outcome);
  const [next, setNext] = useState("");
  const save = useMutation({
    mutationFn: () => updateHearing(h.id, { outcome, ...(next ? { next_date: next } : {}) }),
    onSuccess: () => { toast.success(next ? t("cab.nextScheduled") : t("adm.saved")); setNext(""); onChange(); },
    onError: fail(t("adm.failed")),
  });
  const past = h.date < today();
  return (
    <li className="rounded-xl border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="font-medium">{day(h.date)}{h.time && ` · ${h.time}`}{h.court && ` · ${h.court}`}{h.room && ` (${h.room})`}</span>
        <span className="flex items-center gap-2">
          {past ? <Badge tone="muted">{t("cab.past")}</Badge> : <Badge tone="info">{t("cab.upcoming")}</Badge>}
          <Button size="sm" variant="ghost" onClick={onDelete} aria-label={t("lib.delete")}><Trash2 className="size-3.5" /></Button>
        </span>
      </div>
      {h.purpose && <p className="text-xs text-muted-foreground">{h.purpose}</p>}
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end">
        <Textarea value={outcome} onChange={(e) => setOutcome(e.target.value)} rows={2} placeholder={t("cab.outcome")} aria-label={t("cab.outcome")} className="flex-1" />
        <div className="flex items-end gap-2">
          <label className="text-xs text-muted-foreground">{t("cab.nextDate")}
            <Input type="date" value={next} onChange={(e) => setNext(e.target.value)} className="mt-1 h-9 w-40" /></label>
          <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending || (outcome === h.outcome && !next)}>{t("adm.save")}</Button>
        </div>
      </div>
    </li>
  );
}

function DeadlinesTasks({ m }: { m: MatterDetail }) {
  const { t, num } = useI18n();
  const refresh = useRefresh(m.id);
  const presets = useQuery({ queryKey: ["deadline-presets"], queryFn: deadlinePresets });
  const members = useQuery({ queryKey: ["firm-members"], queryFn: firmMembers });
  const [kind, setKind] = useState("appeal");
  const [start, setStart] = useState(today());
  const [days, setDays] = useState("");
  const [note, setNote] = useState("");
  const [task, setTask] = useState({ title: "", due_on: today(), assigned_to: "" });
  const add = useMutation({
    mutationFn: () => addDeadline(m.id, { kind, start_on: start, ...(days ? { days: Number(days) } : {}), note }),
    onSuccess: () => { setDays(""); setNote(""); refresh(); }, onError: fail(t("adm.failed")),
  });
  const change = useMutation({ mutationFn: (x: { id: number; done?: boolean; verified?: boolean }) => updateDeadline(x.id, x), onSuccess: refresh });
  const newTask = useMutation({ mutationFn: () => addTask({ ...task, matter_id: m.id }),
    onSuccess: () => { setTask({ title: "", due_on: today(), assigned_to: "" }); refresh(); }, onError: fail(t("adm.failed")) });
  const doneTask = useMutation({ mutationFn: (x: { id: number; done: boolean }) => updateTask(x.id, { done: x.done }), onSuccess: refresh });
  const preset = presets.data?.[kind];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title={t("cab.deadlines")}>
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <div className="flex flex-wrap items-end gap-2">
            <Select value={kind} onChange={setKind} label={t("crm.kind")}
                    options={Object.keys(presets.data ?? { appeal: 30 }).map((k) => ({ value: k, label: t(`dl.${k}` as "dl.appeal") }))} />
            <label className="text-xs text-muted-foreground">{t("cab.notifiedOn")}
              <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="mt-1 h-10 w-40" /></label>
            <label className="text-xs text-muted-foreground">{t("cab.days")}
              <Input value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))} placeholder={preset !== undefined ? String(preset) : ""} className="mt-1 h-10 w-20" inputMode="numeric" /></label>
          </div>
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("crm.notes")} className="h-10" aria-label={t("crm.notes")} />
          <Button type="submit" size="sm" disabled={add.isPending}>{t("adm.create")}</Button>
          <p className="text-xs text-amber-700 dark:text-amber-300">{t("cab.deadlineWarning")}</p>
        </form>
        <ul className="mt-4 divide-y text-sm">
          {m.deadlines.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2 py-2">
              <input type="checkbox" checked={!!d.done_at} onChange={(e) => change.mutate({ id: d.id, done: e.target.checked })} aria-label={t("cab.done")} />
              <span className={d.done_at ? "text-muted-foreground line-through" : ""}>
                <b>{day(d.due_on)}</b> · {t(`dl.${d.kind}` as "dl.appeal")} <span className="text-xs text-muted-foreground">({day(d.start_on)} + {num(d.days)} {t("cab.days")})</span>
                {d.note && <span className="text-muted-foreground"> · {d.note}</span>}
              </span>
              {!d.done_at && (d.verified_by ? (
                <Badge tone="good"><ShieldCheck className="me-1 size-3" />{t("cab.verifiedBy")} {d.verified_by}</Badge>
              ) : (
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => change.mutate({ id: d.id, verified: true })}>
                  <ShieldAlert className="size-3.5 text-amber-600" />{t("cab.confirmDeadline")}
                </Button>
              ))}
              {!d.done_at && d.due_on < today() && <Badge tone="bad">{t("cab.late")}</Badge>}
            </li>
          ))}
        </ul>
      </Card>
      <Card title={t("crm.tasks")}>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); newTask.mutate(); }}>
          <Input required value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} placeholder={t("crm.taskTitle")} className="h-10 flex-1" aria-label={t("crm.taskTitle")} />
          <Input type="date" value={task.due_on} onChange={(e) => setTask({ ...task, due_on: e.target.value })} className="h-10 w-40" aria-label={t("bill.due")} />
          <Select value={task.assigned_to} onChange={(v) => setTask({ ...task, assigned_to: v })} label={t("cab.responsible")}
                  options={[{ value: "", label: t("cab.me") }, ...(members.data ?? []).map((x) => ({ value: x.email, label: x.full_name || x.email }))]} />
          <Button type="submit" size="sm" className="h-10">{t("adm.create")}</Button>
        </form>
        <ul className="mt-3 divide-y text-sm">
          {m.tasks.map((x) => (
            <li key={x.id} className="flex items-center gap-2 py-2">
              <input type="checkbox" checked={!!x.done_at} onChange={(e) => doneTask.mutate({ id: x.id, done: e.target.checked })} aria-label={x.title} />
              <span className={x.done_at ? "text-muted-foreground line-through" : ""}>{x.title}</span>
              <span className="ms-auto text-xs text-muted-foreground">{day(x.due_on)} · {x.assigned_to}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function Documents({ m }: { m: MatterDetail }) {
  const { t } = useI18n();
  const refresh = useRefresh(m.id);
  const [busy, setBusy] = useState(false);
  const drop = useMutation({ mutationFn: deleteDocument, onSuccess: refresh });
  const size = (n: number) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} Mo` : `${Math.max(1, Math.round(n / 1024))} Ko`);
  return (
    <Card title={t("cab.documents")} action={
      <label className="inline-flex h-9 cursor-pointer items-center gap-1 rounded-md bg-primary px-3 text-sm text-primary-foreground">
        <Paperclip className="size-4" />{busy ? t("adm.loading") : t("cab.addDocument")}
        <input type="file" multiple className="hidden" onChange={async (e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          setBusy(true);
          try {
            for (const f of files) await uploadDocument(m.id, f);
            refresh();
          } catch (err) {
            toast.error(err instanceof Error ? err.message : t("adm.failed"));
          } finally {
            setBusy(false);
          }
        }} />
      </label>
    }>
      {m.documents.length === 0 ? <Empty>{t("cab.noDocuments")}</Empty> : (
        <ul className="divide-y text-sm">
          {m.documents.map((d) => (
            <li key={d.id} className="flex items-center gap-2 py-2">
              <FileText className="size-4 text-muted-foreground" />
              <button type="button" className="text-start hover:text-teal" onClick={() => downloadDocument(d.id, d.name).catch(() => toast.error(t("adm.failed")))}>{d.name}</button>
              <span className="ms-auto text-xs text-muted-foreground">{size(d.size)} · {d.uploaded_by} · {when(d.uploaded_at)}</span>
              <Button size="sm" variant="ghost" onClick={() => downloadDocument(d.id, d.name)} aria-label={t("ruling.download")}><Download className="size-3.5" /></Button>
              <Button size="sm" variant="ghost" onClick={() => { if (window.confirm(t("cab.deleteDocConfirm"))) drop.mutate(d.id); }} aria-label={t("lib.delete")}><Trash2 className="size-3.5" /></Button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted-foreground">{t("cab.docsPrivate")}</p>
    </Card>
  );
}

function Money({ m }: { m: MatterDetail }) {
  const { t, lang, status } = useI18n();
  const refresh = useRefresh(m.id);
  const navigate = useNavigate();
  const [time, setTime] = useState({ hours: "", description: "", rate: "" });
  const [exp, setExp] = useState({ label: "", amount: "" });
  const [fixed, setFixed] = useState({ label: "", amount: "" });
  const addT = useMutation({
    mutationFn: () => addTime(m.id, { minutes: Math.round(parseFloat(time.hours.replace(",", ".") || "0") * 60), description: time.description, rate: cents(time.rate) }),
    onSuccess: () => { setTime({ ...time, hours: "", description: "" }); refresh(); }, onError: fail(t("adm.failed")),
  });
  const addE = useMutation({ mutationFn: () => addExpense(m.id, { label: exp.label, amount: cents(exp.amount) }),
    onSuccess: () => { setExp({ label: "", amount: "" }); refresh(); }, onError: fail(t("adm.failed")) });
  const dropT = useMutation({ mutationFn: deleteTime, onSuccess: refresh, onError: fail(t("adm.failed")) });
  const dropE = useMutation({ mutationFn: deleteExpense, onSuccess: refresh, onError: fail(t("adm.failed")) });
  const bill = useMutation({
    mutationFn: () => createFeeNote({ matter_id: m.id, include_unbilled: true,
      lines: fixed.label && fixed.amount ? [{ label: fixed.label, amount: cents(fixed.amount) }] : [] }),
    onSuccess: (f) => { refresh(); navigate({ to: "/fee/$feeId", params: { feeId: String(f.id) } }); },
    onError: fail(t("adm.failed")),
  });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title={t("cab.time")}>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); addT.mutate(); }}>
          <Input required value={time.hours} onChange={(e) => setTime({ ...time, hours: e.target.value })} placeholder={t("cab.hours")} className="h-9 w-20" dir="ltr" aria-label={t("cab.hours")} />
          <Input value={time.description} onChange={(e) => setTime({ ...time, description: e.target.value })} placeholder={t("bill.description")} className="h-9 flex-1" aria-label={t("bill.description")} />
          <Input value={time.rate} onChange={(e) => setTime({ ...time, rate: e.target.value })} placeholder={t("cab.rate")} className="h-9 w-28" dir="ltr" aria-label={t("cab.rate")} />
          <Button size="sm" type="submit" className="h-9">{t("adm.create")}</Button>
        </form>
        <ul className="mt-3 divide-y text-sm">
          {m.time.map((x) => (
            <li key={x.id} className="flex items-center gap-2 py-1.5">
              <span>{day(x.date)} · {Math.floor(x.minutes / 60)}h{String(x.minutes % 60).padStart(2, "0")} · {x.description}</span>
              <span className="ms-auto tabular-nums">{money(Math.round(x.minutes * x.rate / 60), lang)}</span>
              {x.fee_invoice_id ? <Badge tone="good">{t("cab.billed")}</Badge> :
                <Button size="sm" variant="ghost" onClick={() => dropT.mutate(x.id)} aria-label={t("lib.delete")}><Trash2 className="size-3.5" /></Button>}
            </li>
          ))}
        </ul>
      </Card>
      <Card title={t("cab.expenses")}>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); addE.mutate(); }}>
          <Input required value={exp.label} onChange={(e) => setExp({ ...exp, label: e.target.value })} placeholder={t("cab.expenseLabel")} className="h-9 flex-1" aria-label={t("cab.expenseLabel")} />
          <Input required value={exp.amount} onChange={(e) => setExp({ ...exp, amount: e.target.value })} placeholder="MAD" className="h-9 w-28" dir="ltr" aria-label={t("bill.amount")} />
          <Button size="sm" type="submit" className="h-9">{t("adm.create")}</Button>
        </form>
        <ul className="mt-3 divide-y text-sm">
          {m.expenses.map((x) => (
            <li key={x.id} className="flex items-center gap-2 py-1.5">
              <span>{day(x.date)} · {x.label}</span>
              <span className="ms-auto tabular-nums">{money(x.amount, lang)}</span>
              {x.fee_invoice_id ? <Badge tone="good">{t("cab.billed")}</Badge> :
                <Button size="sm" variant="ghost" onClick={() => dropE.mutate(x.id)} aria-label={t("lib.delete")}><Trash2 className="size-3.5" /></Button>}
            </li>
          ))}
        </ul>
      </Card>
      <Card title={<span className="flex items-center gap-2"><Receipt className="size-4 text-teal" />{t("cab.feeNotes")}</span>} className="lg:col-span-2">
        <form className="mb-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); bill.mutate(); }}>
          <Input value={fixed.label} onChange={(e) => setFixed({ ...fixed, label: e.target.value })} placeholder={t("cab.fixedFee")} className="h-10 flex-1" aria-label={t("cab.fixedFee")} />
          <Input value={fixed.amount} onChange={(e) => setFixed({ ...fixed, amount: e.target.value })} placeholder="MAD HT" className="h-10 w-32" dir="ltr" aria-label={t("bill.amountHt")} />
          <Button type="submit" disabled={bill.isPending}>{t("cab.makeFeeNote")}</Button>
        </form>
        <p className="mb-3 text-xs text-muted-foreground">{t("cab.feeNoteHint")} ({money(m.unbilled, lang)})</p>
        {m.fee_invoices.length === 0 ? <Empty>{t("bill.none")}</Empty> : (
          <Table head={[t("bill.number"), t("bill.issued"), t("bill.total"), t("bill.balance"), t("adm.colStatus")]} minWidth="30rem">
            {m.fee_invoices.map((f) => (
              <tr key={f.id}>
                <Td><Link to="/fee/$feeId" params={{ feeId: String(f.id) }} className="font-mono text-teal hover:underline" dir="ltr">{f.number}</Link></Td>
                <Td>{day(f.issued_on)}</Td><Td className="tabular-nums">{money(f.amount_ttc, lang)}</Td>
                <Td className="tabular-nums">{money(f.balance, lang)}</Td>
                <Td><Badge tone={STATUS_TONE[f.status]}>{status(f.status)}</Badge></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

function CaseLaw({ m }: { m: MatterDetail }) {
  const { t, lang, num, chamber } = useI18n();
  const refresh = useRefresh(m.id);
  const drop = useMutation({ mutationFn: unlinkRuling, onSuccess: refresh });
  return (
    <Card title={t("cab.caseLaw")} action={<Link to="/browse" className="text-sm text-teal hover:underline">{t("cab.findRulings")}</Link>}>
      <p className="mb-3 text-xs text-muted-foreground">{t("cab.caseLawHint")}</p>
      {m.rulings.length === 0 ? <Empty>{t("cab.noRulings")}</Empty> : (
        <ul className="space-y-3">
          {m.rulings.map((r) => {
            const summary = lang === "fr" ? r.abstract_fr || r.abstract : r.abstract;
            return (
              <li key={r.id} className="rounded-xl border p-3">
                <div className="flex items-start justify-between gap-2">
                  <Link to="/ruling/$docId" params={{ docId: r.doc_id }} className="font-medium hover:text-teal">
                    {t("ruling.decisionOf")} {num(r.decision_no)} · {r.date} · {chamber(r.chamber)}
                  </Link>
                  <Button size="sm" variant="ghost" onClick={() => drop.mutate(r.id)} aria-label={t("lib.remove")}><Trash2 className="size-3.5" /></Button>
                </div>
                {summary && <p className="mt-1 line-clamp-3 text-sm text-muted-foreground" dir={lang === "fr" && r.abstract_fr ? "ltr" : "rtl"}>{summary}</p>}
                {r.note && <p className="mt-1 text-xs">« {r.note} »</p>}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
