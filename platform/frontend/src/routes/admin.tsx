import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ExternalLink, Eye, Save, Upload } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ChamberBadge, LevelBadge, Pill } from "@/components/chips";
import { OutboxPanel, PlansPanel, StaffPanel } from "@/components/AdminPanels";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";
import {
  adminFileUrl, adminGetDecision, adminQueue, correctDecision,
  importBatch, setDecisionState,
  type Decision,
} from "@/lib/api";

export const Route = createFileRoute("/admin")({
  head: () => ({ meta: [{ title: "الإدارة · Administration" }] }),
  component: AdminConsole,
});

function AdminConsole() {
  const navigate = useNavigate();
  const { isAdmin, isSuper, ready } = useStore();
  const { t } = useI18n();
  // only once the session is read: before that everyone looks signed out
  useEffect(() => { if (ready && !isAdmin) navigate({ to: "/browse" }); }, [ready, isAdmin, navigate]);

  return (
    <AppShell title={t("adm.title")} description={t("adm.subtitle")}>
      <Tabs defaultValue="import">
        <TabsList className="h-11 flex-wrap">
          <TabsTrigger value="import" className="px-5">{t("adm.tabImport")}</TabsTrigger>
          <TabsTrigger value="queue" className="px-5">{t("adm.tabQueue")}</TabsTrigger>
          {isSuper && (
            <>
              <TabsTrigger value="staff" className="px-5">{t("adm.tabStaff")}</TabsTrigger>
              <TabsTrigger value="plans" className="px-5">{t("adm.tabPlans")}</TabsTrigger>
              <TabsTrigger value="mail" className="px-5">{t("adm.tabMail")}</TabsTrigger>
            </>
          )}
        </TabsList>
        <TabsContent value="import" className="mt-5"><ImportPanel /></TabsContent>
        <TabsContent value="queue" className="mt-5"><QueuePanel /></TabsContent>
        {isSuper && (
          <>
            <TabsContent value="staff" className="mt-5"><StaffPanel /></TabsContent>
            <TabsContent value="plans" className="mt-5"><PlansPanel /></TabsContent>
            <TabsContent value="mail" className="mt-5"><OutboxPanel /></TabsContent>
          </>
        )}
      </Tabs>
    </AppShell>
  );
}

function ImportPanel() {
  const { t, num } = useI18n();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof importBatch>> | null>(null);

  async function run(file: File) {
    setBusy(true);
    try {
      const r = await importBatch(file);
      setResult(r);
      toast.success(`${t("adm.importDone")} — ${t("adm.imported")} ${num(r.imported)}, ${t("adm.updated")} ${num(r.updated)}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("adm.importFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border bg-card p-6 shadow-soft">
      <h2 className="text-sm font-semibold">{t("adm.importTitle")}</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {t("adm.importHint")}
      </p>
      <input ref={fileRef} type="file" accept=".zip" className="hidden"
        onChange={(e) => e.target.files?.[0] && run(e.target.files[0])} />
      <Button className="mt-4 h-10" disabled={busy} onClick={() => fileRef.current?.click()}>
        <Upload className="size-4" />{busy ? t("adm.importing") : t("adm.choose")}
      </Button>

      {result && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <Stat label={t("adm.imported")} value={result.imported} tone="teal" />
          <Stat label={t("adm.updated")} value={result.updated} tone="muted" />
          <Stat label={t("adm.rejected")} value={result.rejected.length} tone="warn" />
          <Stat label={t("adm.quarantined")} value={result.quarantined.length} tone="warn" />
          {result.quarantined.length > 0 && (
            <div className="sm:col-span-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-xs">
              <p className="font-medium text-destructive">{t("adm.quarantinedList")}</p>
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
  const { t } = useI18n();
  const [rows, setRows] = useState<Decision[]>([]);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const load = () => adminQueue().then(setRows).catch(() => setRows([]));
  useEffect(() => { load(); }, []);

  async function publish(id: string) {
    try { await setDecisionState(id, "published"); toast.success(`${t("adm.published")} ${id}`); load(); }
    catch (e) { toast.error(e instanceof Error ? e.message : t("adm.failed")); }
  }

  return (
    <div className="overflow-auto rounded-2xl border bg-card shadow-soft">
      <table className="w-full min-w-[760px] text-sm">
        <thead>
          <tr className="border-b text-start text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-3 text-start">{t("adm.colDecision")}</th>
            <th className="px-4 py-3 text-start">{t("col.chamber")}</th>
            <th className="px-4 py-3 text-start">{t("col.level")}</th>
            <th className="px-4 py-3 text-start">{t("adm.colAttention")}</th>
            <th className="px-4 py-3 text-end">{t("adm.colAction")}</th>
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
                    <Eye className="size-4" />{t("adm.review")}
                  </Button>
                  <Button size="sm" className="h-8" onClick={() => publish(d.doc_id)}>
                    <CheckCircle2 className="size-4" />{t("adm.publish")}
                  </Button>
                </div>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">{t("adm.queueClear")}</td></tr>
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
  const { t } = useI18n();
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
    try { await correctDecision(docId, form); toast.success(t("adm.saved")); onChanged(); }
    catch (e) { toast.error(e instanceof Error ? e.message : t("adm.failed")); }
    finally { setBusy(false); }
  }
  async function publish() {
    if (!docId) return;
    setBusy(true);
    try { await setDecisionState(docId, "published"); toast.success(t("adm.published")); onChanged(); onClose(); }
    catch (e) { toast.error(e instanceof Error ? e.message : t("adm.failed")); }
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
          <DialogTitle className="text-sm">{t("adm.review")} · {d?.decision_no || docId}</DialogTitle>
        </DialogHeader>
        {!d ? (
          <p className="px-5 py-10 text-center text-sm text-muted-foreground">{t("adm.loading")}</p>
        ) : (
          <div className="grid gap-0 md:grid-cols-[300px_minmax(0,1fr)]">
            {/* editable fields + actions */}
            <div className="space-y-3 border-e p-5">
              {F(t("col.chamber"), "category", true)}
              {F(t("col.number"), "decision_no", true)}
              {F(t("col.fileNo"), "file_no", true)}
              {F(t("col.date"), "decision_date", true)}
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="outline" className="h-9" disabled={busy} onClick={save}>
                  <Save className="size-4" />{t("adm.save")}
                </Button>
                <Button size="sm" className="h-9" disabled={busy} onClick={publish}>
                  <CheckCircle2 className="size-4" />{t("adm.publish")}
                </Button>
              </div>
              <Button size="sm" variant="ghost" className="h-9 w-full" asChild>
                <a href={adminFileUrl(d.doc_id)} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-4" />{t("adm.openFile")}
                </a>
              </Button>
              {d.review_notes && d.review_notes.length > 0 && (
                <div className="rounded-lg border border-warning/40 bg-warning/10 p-2 text-xs">
                  <b>{t("adm.verify")}</b> {d.review_notes.join("، ")}
                </div>
              )}
            </div>
            {/* anonymized text preview */}
            <div dir="rtl" className="max-h-[62vh] overflow-auto p-5">
              <p className="mb-2 text-xs text-muted-foreground">
                {t("adm.anonText")} <code className="font-mono">XXXXXXX</code>
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
                {!d.body_text && <p className="text-muted-foreground">{t("adm.noText")}</p>}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
