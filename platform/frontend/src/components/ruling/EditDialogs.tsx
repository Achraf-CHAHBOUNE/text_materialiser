import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  hideAll, previewHideAll, previewText, reportProblem, saveText, type DiffHunk,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

import { DiffView } from "./DiffView";
import { useEdits } from "./useEdits";

/** «hit» markers from the server, drawn as highlights. */
export function Snippet({ text }: { text: string }) {
  return (
    <>
      {text.split(/(«[^»]*»)/g).map((c, i) =>
        c.startsWith("«") ? (
          <mark key={i} className="rounded bg-amber-300/50 px-0.5">{c.slice(1, -1)}</mark>
        ) : (
          <span key={i}>{c}</span>
        ),
      )}
    </>
  );
}

/** Kind of change, said plainly before anything is saved. */
export function ChangeKind({ removal }: { removal: boolean }) {
  const { t } = useI18n();
  return removal ? (
    <p className="flex items-start gap-2 rounded-xl bg-emerald-500/10 px-3 py-2 text-sm text-emerald-800 dark:text-emerald-300">
      <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden /> {t("edit.goesLive")}
    </p>
  ) : (
    <p className="flex items-start gap-2 rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-300">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {t("edit.needsApproval")}
    </p>
  );
}

export function GateWarning({ findings }: { findings: string[] }) {
  const { t } = useI18n();
  if (!findings.length) return null;
  return (
    <p className="rounded-xl bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {t("edit.gate")}: {findings.join(" · ")}
    </p>
  );
}

export function HideAllDialog({ docId, version, value, onClose }: {
  docId: string; version: number; value: string | null; onClose: () => void;
}) {
  const { t, num, dir } = useI18n();
  const { applyOutcome, fail } = useEdits(docId);
  const preview = useQuery({
    queryKey: ["hide-all-preview", docId, version, value],
    queryFn: () => previewHideAll(docId, value ?? "", version),
    enabled: !!value,
    retry: false,
  });
  const apply = useMutation({
    mutationFn: () => hideAll(docId, value ?? "", version),
    onSuccess: (out) => { applyOutcome(out, "hide_all"); onClose(); },
    onError: fail,
  });
  const count = preview.data?.count ?? 0;

  return (
    <Dialog open={!!value} onOpenChange={(o) => !o && onClose()}>
      <DialogContent dir={dir} className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("edit.hideAllTitle")}</DialogTitle>
          <DialogDescription>{t("edit.hideAllNote")}</DialogDescription>
        </DialogHeader>
        <p dir="rtl" className="rounded-xl bg-muted px-3 py-2 font-medium">{value}</p>
        {preview.isLoading && <p className="text-sm text-muted-foreground">…</p>}
        {preview.error && <p className="text-sm text-destructive">{(preview.error as Error).message}</p>}
        {preview.data && (
          count === 0 ? (
            <p className="text-sm text-muted-foreground">{t("edit.none")}</p>
          ) : (
            <>
              <p className="text-sm"><b className="tabular-nums">{num(count)}</b> {t("edit.occurrences")}</p>
              <ul dir="rtl" className="max-h-60 space-y-2 overflow-y-auto text-sm leading-7">
                {preview.data.snippets.map((s, i) => (
                  <li key={i} className="rounded-lg border px-3 py-1.5"><Snippet text={s} /></li>
                ))}
              </ul>
            </>
          )
        )}
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={onClose}>{t("edit.cancel")}</Button>
          <Button disabled={!count || apply.isPending} onClick={() => apply.mutate()}>
            {t("edit.hideAllConfirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TextEditorDialog({ docId, version, text, open, onClose }: {
  docId: string; version: number; text: string; open: boolean; onClose: () => void;
}) {
  const { t, dir } = useI18n();
  const { applyOutcome, fail } = useEdits(docId);
  const [draft, setDraft] = useState(text);
  const [review, setReview] = useState<{ removal: boolean; diff: DiffHunk[]; gate: string[] } | null>(null);

  useEffect(() => {
    if (open) { setDraft(text); setReview(null); }
  }, [open, text]);

  const check = useMutation({
    mutationFn: () => previewText(docId, draft, version),
    onSuccess: setReview,
    onError: fail,
  });
  const save = useMutation({
    mutationFn: () => saveText(docId, draft, version),
    onSuccess: (out) => { applyOutcome(out, "edit"); onClose(); },
    onError: fail,
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent dir={dir} className="flex max-h-[92vh] max-w-4xl flex-col">
        <DialogHeader>
          <DialogTitle>{review ? t("edit.review") : t("edit.editText")}</DialogTitle>
        </DialogHeader>
        {review ? (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
            {review.diff.length > 0 && <ChangeKind removal={review.removal} />}
            <GateWarning findings={review.gate} />
            <DiffView hunks={review.diff} />
          </div>
        ) : (
          <Textarea
            dir="rtl"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="min-h-[60vh] flex-1 font-arabic text-[15px] leading-8"
          />
        )}
        <DialogFooter className="gap-2">
          {review ? (
            <>
              <Button variant="ghost" onClick={() => setReview(null)}>{t("edit.back")}</Button>
              <Button
                disabled={!review.diff.length || review.gate.length > 0 || save.isPending}
                variant={review.removal ? "default" : "secondary"}
                onClick={() => save.mutate()}
              >
                {review.removal ? t("edit.saveLive") : t("edit.saveDraft")}
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose}>{t("edit.cancel")}</Button>
              <Button disabled={draft === text || check.isPending} onClick={() => check.mutate()}>
                {t("edit.review")}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ReportDialog({ docId, quote, open, onClose }: {
  docId: string; quote: string; open: boolean; onClose: () => void;
}) {
  const { t, dir } = useI18n();
  const [note, setNote] = useState("");
  useEffect(() => { if (open) setNote(""); }, [open]);
  const send = useMutation({
    mutationFn: () => reportProblem(docId, quote, note),
    onSuccess: () => { toast.success(t("report.sent")); onClose(); },
    onError: (e) => toast.error(e instanceof Error ? e.message : String(e)),
  });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent dir={dir} className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("report.title")}</DialogTitle>
          <DialogDescription>{t("report.hint")}</DialogDescription>
        </DialogHeader>
        {quote && (
          <div>
            <p className="mb-1 text-xs text-muted-foreground">{t("report.quote")}</p>
            <p dir="rtl" className="rounded-xl bg-muted px-3 py-2">{quote}</p>
          </div>
        )}
        <div>
          <p className="mb-1 text-xs text-muted-foreground">{t("report.note")}</p>
          <Textarea value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
        </div>
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={onClose}>{t("edit.cancel")}</Button>
          <Button disabled={(!quote && !note.trim()) || send.isPending} onClick={() => send.mutate()}>
            {t("report.send")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
