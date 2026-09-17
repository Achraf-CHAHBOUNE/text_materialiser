import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight, Download, Flag, PencilLine, Printer, SquarePen } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { DetailsForm } from "@/components/ruling/DetailsForm";
import { HideAllDialog, ReportDialog, TextEditorDialog } from "@/components/ruling/EditDialogs";
import { HistoryPanel } from "@/components/ruling/HistoryPanel";
import { RulingText, type Selected } from "@/components/ruling/RulingText";
import { rulingKey, useEdits } from "@/components/ruling/useEdits";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { adminFileUrl, adminGetDecision, decisionFileUrl, getDecision, hideText } from "@/lib/api";
import { useStore } from "@/lib/app-store";
import { chamberStyle } from "@/lib/chambers";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/ruling/$docId")({
  component: RulingPage,
});

function RulingPage() {
  const { docId } = Route.useParams();
  const { isAdmin } = useStore();
  const { t, dir, lang, num, chamber: chamberName, court: courtName, city: cityName } = useI18n();
  // An admin reads through the admin route: it also opens rulings not yet published.
  const ruling = useQuery({
    queryKey: rulingKey(docId, isAdmin),
    queryFn: () => (isAdmin ? adminGetDecision(docId) : getDecision(docId)),
  });
  const d = ruling.data;
  const style = chamberStyle(d?.category ?? "");
  const version = d?.version ?? 0;

  const { applyOutcome, fail } = useEdits(docId);
  const [hideAllValue, setHideAllValue] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [details, setDetails] = useState(false);
  const [report, setReport] = useState<string | null>(null);

  const hide = useMutation({
    mutationFn: (s: Selected) => hideText(docId, { value: s.value, occurrence: s.occurrence ?? 0, base_version: version }),
    onSuccess: (out) => applyOutcome(out, "hide"),
    onError: fail,
  });

  return (
    <AppShell>
      <div dir={dir} className={`font-arabic mx-auto w-full ${isAdmin ? "max-w-6xl" : "max-w-4xl"}`}>
        <nav className="mb-3 flex items-center gap-1 text-sm text-muted-foreground">
          <Link to="/browse" className="hover:text-foreground">{t("browse.title")}</Link>
          {d && (
            <>
              <ChevronRight className={`size-4 ${lang === "ar" ? "rotate-180" : ""}`} aria-hidden />
              <Link to="/browse/$chamber" params={{ chamber: d.category }} className="hover:text-foreground">
                {chamberName(d.category)}
              </Link>
            </>
          )}
        </nav>

        {ruling.isLoading && <Skeleton className="h-40 w-full rounded-2xl" />}
        {ruling.error && (
          <p className="rounded-2xl border bg-card px-5 py-10 text-center text-sm text-destructive">
            {t("ruling.error")}
          </p>
        )}

        {d && (
          <div className={isAdmin ? "grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]" : ""}>
            <div className="min-w-0">
              <header className={`rounded-2xl px-5 py-4 shadow-sm ${style.solid}`}>
                <h1 className="text-lg font-semibold sm:text-xl">
                  {courtName(d.court || "محكمة النقض")} — {t("ruling.decisionOf")} {d.decision_no ? num(d.decision_no) : "—"}
                </h1>
                <p className="mt-0.5 text-xs opacity-90">
                  {chamberName(d.category)} · {d.date ? num(d.date) : t("ruling.noDate")}
                  {d.city ? ` · ${cityName(d.city)}` : ""}
                  {isAdmin && d.edited_at ? ` · ${t("edit.edited")}` : ""}
                </p>
              </header>

              {details && isAdmin ? (
                <DetailsForm key={`${d.doc_id}:${d.updated_at}`} d={d} onDone={() => setDetails(false)} />
              ) : (
                <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Field label={t("col.number")} value={d.decision_no ? num(d.decision_no) : ""} />
                  <Field label={t("col.date")} value={d.date ? num(d.date) : ""} />
                  <Field label={t("col.city")} value={d.city ? cityName(d.city) : ""} />
                  <Field label={t("col.fileNo")} value={d.file_no ? num(d.file_no) : ""} />
                </dl>
              )}

              <div className="mt-4 flex flex-wrap gap-2">
                <Button asChild size="sm">
                  <a href={isAdmin ? adminFileUrl(d.doc_id) : decisionFileUrl(d.doc_id)} download>
                    <Download className="size-4" aria-hidden /> {t("ruling.download")}
                  </a>
                </Button>
                <Button variant="outline" size="sm" onClick={() => window.print()}>
                  <Printer className="size-4" aria-hidden /> {t("ruling.print")}
                </Button>
                {isAdmin ? (
                  <>
                    <Button variant="outline" size="sm" onClick={() => setEditing(true)} disabled={!d.body_text}>
                      <PencilLine className="size-4" aria-hidden /> {t("edit.editText")}
                    </Button>
                    {!details && (
                      <Button variant="outline" size="sm" onClick={() => setDetails(true)}>
                        <SquarePen className="size-4" aria-hidden /> {t("edit.editDetails")}
                      </Button>
                    )}
                  </>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => setReport("")}>
                    <Flag className="size-4" aria-hidden /> {t("report.title")}
                  </Button>
                )}
              </div>
              {isAdmin && d.body_text && (
                <p className="mt-3 text-xs text-muted-foreground">{t("edit.selectHint")}</p>
              )}

              {/* The ruling's own words: always Arabic, never translated. */}
              {d.body_text ? (
                <RulingText
                  text={d.body_text}
                  canEdit={isAdmin}
                  busy={hide.isPending}
                  onHide={(s) => hide.mutate(s)}
                  onHideAll={setHideAllValue}
                  onReport={setReport}
                />
              ) : (
                <p className="mt-4 rounded-2xl border bg-card p-6 text-sm">{t("ruling.noText")}</p>
              )}

              <p className="mt-3 text-xs text-muted-foreground">{t("ruling.notice")}</p>
            </div>

            {isAdmin && <HistoryPanel docId={d.doc_id} version={version} />}
          </div>
        )}
      </div>

      {d && isAdmin && (
        <>
          <HideAllDialog docId={d.doc_id} version={version} value={hideAllValue} onClose={() => setHideAllValue(null)} />
          <TextEditorDialog docId={d.doc_id} version={version} text={d.body_text ?? ""} open={editing}
                            onClose={() => setEditing(false)} />
        </>
      )}
      {d && !isAdmin && (
        <ReportDialog docId={d.doc_id} quote={report ?? ""} open={report !== null} onClose={() => setReport(null)} />
      )}
    </AppShell>
  );
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-xl border bg-card px-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums">{value || "—"}</dd>
    </div>
  );
}
