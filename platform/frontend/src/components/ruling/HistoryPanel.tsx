import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Flag, History as HistoryIcon, Trash2 } from "lucide-react";
import { useState } from "react";

import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  approveDraft, discardDraft, getDraft, purgeHistory, resolveReport, restoreVersion, rulingHistory,
  versionDiff, type VersionRow,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

import { DiffView } from "./DiffView";
import { ChangeKind, GateWarning } from "./EditDialogs";
import { historyKey, useActionLabel, useEdits, useSummary } from "./useEdits";

const when = (iso: string) => (iso ? iso.slice(0, 16).replace("T", " ") : "");

export function HistoryPanel({ docId, version }: { docId: string; version: number }) {
  const { t, num } = useI18n();
  const label = useActionLabel();
  const summary = useSummary();
  const qc = useQueryClient();
  const { applyOutcome, fail } = useEdits(docId);
  const history = useQuery({ queryKey: historyKey(docId), queryFn: () => rulingHistory(docId) });
  const [restoring, setRestoring] = useState<number | null>(null);
  const [draft, setDraft] = useState<number | null>(null);
  const [purging, setPurging] = useState(false);

  const purge = useMutation({ mutationFn: () => purgeHistory(docId), onSuccess: (o) => applyOutcome(o), onError: fail });
  const resolve = useMutation({
    mutationFn: (p: { id: number; status: "resolved" | "dismissed" }) => resolveReport(p.id, p.status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: historyKey(docId) });
      void qc.invalidateQueries({ queryKey: ["corrections"] });
    },
    onError: fail,
  });

  const h = history.data;
  const versions = h?.versions ?? [];
  const drafts = h?.drafts ?? [];
  const reports = h?.reports ?? [];

  return (
    <aside className="space-y-4">
      {reports.length > 0 && (
        <section className="rounded-2xl border border-amber-500/40 bg-card p-4">
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Flag className="size-4 text-amber-600" aria-hidden /> {t("history.reports")} ({num(reports.length)})
          </h2>
          <ul className="space-y-3">
            {reports.map((r) => (
              <li key={r.id} className="rounded-xl bg-muted/50 p-3 text-sm">
                {r.quote && <p dir="rtl" className="font-medium">«{r.quote}»</p>}
                {r.note && <p className="mt-1 text-muted-foreground">{r.note}</p>}
                <p className="mt-1 text-xs text-muted-foreground">{r.reporter} · {when(r.created_at)}</p>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="outline" disabled={resolve.isPending}
                          onClick={() => resolve.mutate({ id: r.id, status: "resolved" })}>
                    {t("history.resolve")}
                  </Button>
                  <Button size="sm" variant="ghost" disabled={resolve.isPending}
                          onClick={() => resolve.mutate({ id: r.id, status: "dismissed" })}>
                    {t("history.dismiss")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {drafts.length > 0 && (
        <section className="rounded-2xl border border-amber-500/40 bg-card p-4">
          <h2 className="mb-2 text-sm font-semibold">{t("history.drafts")}</h2>
          <ul className="space-y-2">
            {drafts.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0">
                  <span className="font-medium">{label(d.action)}</span>
                  <span className="text-muted-foreground"> · {summary(d.summary)}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {t("history.by")} {d.actor} · {when(d.created_at)}
                  </span>
                </span>
                <Button size="sm" variant="outline" onClick={() => setDraft(d.id)}>{t("history.open")}</Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-2xl border bg-card p-4">
        <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <HistoryIcon className="size-4" aria-hidden /> {t("history.title")}
        </h2>
        {versions.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("history.empty")}</p>
        ) : (
          <ol className="space-y-2">
            {versions.map((v: VersionRow) => (
              <li key={v.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0">
                  <span className="font-medium tabular-nums">v{num(v.version ?? 0)}</span>{" "}
                  <span>{label(v.action)}</span>
                  {v.summary && v.action !== "import" && <span className="text-muted-foreground"> · {summary(v.summary)}</span>}
                  <span className="block truncate text-xs text-muted-foreground">
                    {v.actor} · {when(v.decided_at || v.created_at)}
                  </span>
                </span>
                {v.version === version ? (
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{t("history.current")}</span>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => setRestoring(v.version)}>{t("history.restore")}</Button>
                )}
              </li>
            ))}
          </ol>
        )}
        {versions.length > 1 && (
          <Button size="sm" variant="ghost" className="mt-3 text-destructive" onClick={() => setPurging(true)}>
            <Trash2 className="size-4" aria-hidden /> {t("history.purge")}
          </Button>
        )}
      </section>

      <RestoreDialog docId={docId} version={version} target={restoring} onClose={() => setRestoring(null)} />
      <DraftDialog docId={docId} draftId={draft} onClose={() => setDraft(null)} />

      <AlertDialog open={purging} onOpenChange={setPurging}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("history.purge")}</AlertDialogTitle>
            <AlertDialogDescription>{t("history.purgeBody")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("edit.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => purge.mutate()}>{t("history.purge")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  );
}

function RestoreDialog({ docId, version, target, onClose }: {
  docId: string; version: number; target: number | null; onClose: () => void;
}) {
  const { t, num, dir } = useI18n();
  const { applyOutcome, fail } = useEdits(docId);
  const diff = useQuery({
    queryKey: ["version-diff", docId, target, version],
    queryFn: () => versionDiff(docId, target ?? 0),
    enabled: target !== null,
  });
  const restore = useMutation({
    mutationFn: () => restoreVersion(docId, target ?? 0, version),
    onSuccess: (o) => { applyOutcome(o, "restore"); onClose(); },
    onError: fail,
  });
  return (
    <Dialog open={target !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent dir={dir} className="flex max-h-[90vh] max-w-3xl flex-col">
        <DialogHeader>
          <DialogTitle>{t("history.restoreTitle")} v{num(target ?? 0)}</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
          {diff.data && diff.data.diff.length > 0 && <ChangeKind removal={diff.data.removal} />}
          {diff.data && <DiffView hunks={diff.data.diff} />}
          {diff.error && <p className="text-sm text-destructive">{(diff.error as Error).message}</p>}
        </div>
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={onClose}>{t("edit.cancel")}</Button>
          <Button disabled={!diff.data?.diff.length || restore.isPending} onClick={() => restore.mutate()}>
            {diff.data?.removal === false ? t("edit.saveDraft") : t("history.restore")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DraftDialog({ docId, draftId, onClose }: { docId: string; draftId: number | null; onClose: () => void }) {
  const { t, dir } = useI18n();
  const label = useActionLabel();
  const { applyOutcome, fail } = useEdits(docId);
  const draft = useQuery({
    queryKey: ["draft", draftId],
    queryFn: () => getDraft(draftId ?? 0),
    enabled: draftId !== null,
    staleTime: 0,
  });
  const approve = useMutation({
    mutationFn: () => approveDraft(draftId ?? 0),
    onSuccess: (o) => { applyOutcome(o, draft.data?.action); onClose(); },
    onError: fail,
  });
  const discard = useMutation({
    mutationFn: () => discardDraft(draftId ?? 0),
    onSuccess: (o) => { applyOutcome(o); onClose(); },
    onError: fail,
  });
  const d = draft.data;
  return (
    <Dialog open={draftId !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent dir={dir} className="flex max-h-[90vh] max-w-3xl flex-col">
        <DialogHeader>
          <DialogTitle>{d ? `${label(d.action)} · ${d.actor}` : "…"}</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
          {d?.stale && (
            <p className="rounded-xl bg-destructive/10 px-3 py-2 text-sm text-destructive">{t("history.stale")}</p>
          )}
          {d && <GateWarning findings={d.gate} />}
          {d && <DiffView hunks={d.diff} />}
        </div>
        <DialogFooter className="gap-2">
          <Button variant="ghost" className="text-destructive" disabled={discard.isPending} onClick={() => discard.mutate()}>
            {t("history.discard")}
          </Button>
          <Button disabled={!d || d.stale || d.gate.length > 0 || approve.isPending} onClick={() => approve.mutate()}>
            {t("history.approve")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
