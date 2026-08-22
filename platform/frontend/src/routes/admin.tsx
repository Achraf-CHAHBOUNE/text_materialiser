import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Ban, CheckCircle2, ExternalLink, Eye, Save, Trash2, Upload, UserPlus } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ChamberBadge, LevelBadge, Pill } from "@/components/chips";
import { useStore } from "@/lib/app-store";
import {
  adminFileUrl, adminGetDecision, adminQueue, correctDecision, createClient, deleteClient,
  importBatch, listClients, setDecisionState, updateClient,
  type ClientAccount, type Decision,
} from "@/lib/api";

export const Route = createFileRoute("/admin")({
  head: () => ({ meta: [{ title: "Admin console — القرارات" }] }),
  component: AdminConsole,
});

function AdminConsole() {
  const navigate = useNavigate();
  const { isAdmin } = useStore();
  useEffect(() => { if (!isAdmin) navigate({ to: "/dashboard" }); }, [isAdmin, navigate]);

  return (
    <AppShell title="Admin console" description="Import, review, publish, and manage clients">
      <Tabs defaultValue="import">
        <TabsList className="h-11">
          <TabsTrigger value="import" className="px-5">Import</TabsTrigger>
          <TabsTrigger value="queue" className="px-5">Review queue</TabsTrigger>
          <TabsTrigger value="clients" className="px-5">Clients</TabsTrigger>
        </TabsList>
        <TabsContent value="import" className="mt-5"><ImportPanel /></TabsContent>
        <TabsContent value="queue" className="mt-5"><QueuePanel /></TabsContent>
        <TabsContent value="clients" className="mt-5"><ClientsPanel /></TabsContent>
      </Tabs>
    </AppShell>
  );
}

function ImportPanel() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof importBatch>> | null>(null);

  async function run(file: File) {
    setBusy(true);
    try {
      const r = await importBatch(file);
      setResult(r);
      toast.success(`Imported ${r.imported}, updated ${r.updated}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border bg-card p-6 shadow-soft">
      <h2 className="text-sm font-semibold">Import a pipeline batch (.zip)</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        The archive must contain <code>records.json</code> and the anonymized files. The import gate
        re-checks every file for PII and refuses anything that still looks personal.
      </p>
      <input ref={fileRef} type="file" accept=".zip" className="hidden"
        onChange={(e) => e.target.files?.[0] && run(e.target.files[0])} />
      <Button className="mt-4 h-10" disabled={busy} onClick={() => fileRef.current?.click()}>
        <Upload className="size-4" />{busy ? "Importing…" : "Choose .zip"}
      </Button>

      {result && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <Stat label="Imported" value={result.imported} tone="teal" />
          <Stat label="Updated" value={result.updated} tone="muted" />
          <Stat label="Rejected (no file)" value={result.rejected.length} tone="warn" />
          <Stat label="Quarantined (PII)" value={result.quarantined.length} tone="warn" />
          {result.quarantined.length > 0 && (
            <div className="sm:col-span-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-xs">
              <p className="font-medium text-destructive">Quarantined — still contains PII patterns:</p>
              <ul className="mt-1 space-y-0.5">
                {result.quarantined.map((q) => (
                  <li key={q.doc_id}><b>{q.doc_id}</b>: {q.findings.join(", ")}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "teal" | "muted" | "warn" }) {
  const cls = tone === "teal" ? "text-teal" : tone === "warn" ? "text-destructive" : "text-foreground";
  return (
    <div className="rounded-xl border bg-background p-4">
      <p className={`text-2xl font-semibold tabular-nums ${cls}`}>{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function QueuePanel() {
  const [rows, setRows] = useState<Decision[]>([]);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const load = () => adminQueue().then(setRows).catch(() => setRows([]));
  useEffect(() => { load(); }, []);

  async function publish(id: string) {
    try { await setDecisionState(id, "published"); toast.success(`Published ${id}`); load(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <div className="overflow-auto rounded-2xl border bg-card shadow-soft">
      <table className="w-full min-w-[760px] text-sm">
        <thead>
          <tr className="border-b text-start text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-3 text-start">Decision</th>
            <th className="px-4 py-3 text-start">الغرفة</th>
            <th className="px-4 py-3 text-start">Level</th>
            <th className="px-4 py-3 text-start">Needs attention</th>
            <th className="px-4 py-3 text-end">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((d) => (
            <tr key={d.doc_id} className="cursor-pointer odd:bg-muted/25 hover:bg-teal/6"
              onClick={() => setReviewId(d.doc_id)}>
              <td className="px-4 py-3 font-medium">{d.decision_no || d.doc_id}</td>
              <td className="px-4 py-3"><ChamberBadge chamber={d.category} /></td>
              <td className="px-4 py-3"><LevelBadge level={d.level} /></td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1">
                  {(d.reasons || []).map((r) => <Pill key={r} tone="muted">{r}</Pill>)}
                </div>
              </td>
              <td className="px-4 py-3 text-end" onClick={(e) => e.stopPropagation()}>
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="outline" className="h-8" onClick={() => setReviewId(d.doc_id)}>
                    <Eye className="size-4" />Review
                  </Button>
                  <Button size="sm" className="h-8" onClick={() => publish(d.doc_id)}>
                    <CheckCircle2 className="size-4" />Publish
                  </Button>
                </div>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">Queue is clear.</td></tr>
          )}
        </tbody>
      </table>
      <ReviewDialog docId={reviewId} onClose={() => setReviewId(null)}
        onChanged={() => { load(); }} />
    </div>
  );
}

function ReviewDialog({ docId, onClose, onChanged }:
  { docId: string | null; onClose: () => void; onChanged: () => void }) {
  const [d, setD] = useState<Decision | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!docId) { setD(null); return; }
    adminGetDecision(docId).then((dec) => {
      setD(dec);
      setForm({ category: dec.category, decision_no: dec.decision_no,
        file_no: dec.file_no, decision_date: dec.date });
    }).catch(() => setD(null));
  }, [docId]);

  async function save() {
    if (!docId) return;
    setBusy(true);
    try { await correctDecision(docId, form); toast.success("Saved"); onChanged(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(false); }
  }
  async function publish() {
    if (!docId) return;
    setBusy(true);
    try { await setDecisionState(docId, "published"); toast.success("Published"); onChanged(); onClose(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(false); }
  }

  const F = (label: string, key: string, ar = false) => (
    <label className="block">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Input value={form[key] ?? ""} onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        className={"h-9 " + (ar ? "font-ar" : "")} />
    </label>
  );

  return (
    <Dialog open={!!docId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl gap-0 p-0">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="text-sm">Review · {d?.decision_no || docId}</DialogTitle>
        </DialogHeader>
        {!d ? (
          <p className="px-5 py-10 text-center text-sm text-muted-foreground">Loading…</p>
        ) : (
          <div className="grid gap-0 md:grid-cols-[300px_minmax(0,1fr)]">
            {/* editable fields + actions */}
            <div className="space-y-3 border-e p-5">
              {F("الغرفة (chamber)", "category", true)}
              {F("رقم القرار", "decision_no", true)}
              {F("رقم الملف", "file_no", true)}
              {F("التاريخ", "decision_date", true)}
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="outline" className="h-9" disabled={busy} onClick={save}>
                  <Save className="size-4" />Save
                </Button>
                <Button size="sm" className="h-9" disabled={busy} onClick={publish}>
                  <CheckCircle2 className="size-4" />Publish
                </Button>
              </div>
              <Button size="sm" variant="ghost" className="h-9 w-full" asChild>
                <a href={adminFileUrl(d.doc_id)} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-4" />Open file (.docx)
                </a>
              </Button>
              {d.review_notes && d.review_notes.length > 0 && (
                <div className="rounded-lg border border-warning/40 bg-warning/10 p-2 text-xs">
                  <b>Verify flagged:</b> {d.review_notes.join("، ")}
                </div>
              )}
            </div>
            {/* anonymized text preview */}
            <div dir="rtl" className="max-h-[62vh] overflow-auto p-5">
              <p className="mb-2 text-xs text-muted-foreground">
                النص المجهول — الأسماء مستبدلة بـ <code className="font-mono">XXXXXXX</code>
              </p>
              <div className="font-ar space-y-2 text-[14px] leading-loose">
                {(d.body_text || "").split("\n").map((line, i) =>
                  line.trim() ? (
                    <p key={i}>
                      {line.split(/(XXXXXXX)/g).map((c, k) =>
                        c === "XXXXXXX" ? (
                          <mark key={k} className="rounded bg-teal/15 px-1 font-mono text-teal">XXXXXXX</mark>
                        ) : <span key={k}>{c}</span>,
                      )}
                    </p>
                  ) : null,
                )}
                {!d.body_text && <p className="text-muted-foreground">No text preview.</p>}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ClientsPanel() {
  const [clients, setClients] = useState<ClientAccount[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const load = () => listClients().then(setClients).catch(() => setClients([]));
  useEffect(() => { load(); }, []);

  async function add() {
    if (!email || password.length < 6) { toast.error("Email + 6-char password required"); return; }
    try { await createClient(email, password); setEmail(""); setPassword(""); toast.success("Client created"); load(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
  }
  async function toggle(c: ClientAccount) {
    const next = c.status === "active" ? "suspended" : "active";
    try { await updateClient(c.email, { status: next }); toast.success(`${c.email} ${next}`); load(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
  }
  async function remove(c: ClientAccount) {
    try { await deleteClient(c.email); toast.success(`Deleted ${c.email}`); load(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border bg-card p-5 shadow-soft">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><UserPlus className="size-4 text-teal" />New client</h2>
        <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <Input placeholder="client@firm.ma" value={email} onChange={(e) => setEmail(e.target.value)} className="h-10" />
          <Input placeholder="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="h-10" />
          <Button className="h-10" onClick={add}>Create</Button>
        </div>
      </div>

      <div className="overflow-auto rounded-2xl border bg-card shadow-soft">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b text-start text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-3 text-start">Email</th>
              <th className="px-4 py-3 text-start">Status</th>
              <th className="px-4 py-3 text-start">Last login</th>
              <th className="px-4 py-3 text-end">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {clients.map((c) => (
              <tr key={c.email} className="odd:bg-muted/25">
                <td className="px-4 py-3 font-medium">{c.email}</td>
                <td className="px-4 py-3">
                  <Pill tone={c.status === "active" ? "success" : "muted"}>{c.status}</Pill>
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{c.last_login ? c.last_login.slice(0, 16).replace("T", " ") : "—"}</td>
                <td className="px-4 py-3 text-end">
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" className="h-8" onClick={() => toggle(c)}>
                      <Ban className="size-3.5" />{c.status === "active" ? "Suspend" : "Activate"}
                    </Button>
                    <Button size="sm" variant="outline" className="h-8 text-destructive" onClick={() => remove(c)}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {clients.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-12 text-center text-sm text-muted-foreground">No clients yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
