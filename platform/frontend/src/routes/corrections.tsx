import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Download, FileText, Flag } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { useActionLabel, useSummary } from "@/components/ruling/useEdits";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { editsExportUrl, listDrafts, listReports } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/corrections")({
  head: () => ({ meta: [{ title: "التصحيحات — Corrections" }] }),
  component: Corrections,
});

const when = (iso: string) => (iso ? iso.slice(0, 16).replace("T", " ") : "");

/** Everything waiting for an admin: what readers reported, and edits to approve. */
function Corrections() {
  const { t, dir, num, chamber } = useI18n();
  const label = useActionLabel();
  const summary = useSummary();
  const reports = useQuery({ queryKey: ["corrections", "reports"], queryFn: () => listReports("open") });
  const drafts = useQuery({ queryKey: ["corrections", "drafts"], queryFn: listDrafts });

  const ruling = (docId: string, no: string | undefined, cat: string | undefined) => (
    <Link to="/ruling/$docId" params={{ docId }} className="font-medium text-primary hover:underline">
      {t("ruling.decisionOf")} {no ? num(no) : docId}
      {cat ? <span className="text-muted-foreground"> · {chamber(cat)}</span> : null}
    </Link>
  );

  return (
    <AppShell
      title={t("nav.review")}
      description={t("review.subtitle")}
      action={
        <Button asChild size="sm" variant="outline">
          <a href={editsExportUrl()}><Download className="size-4" aria-hidden /> {t("review.export")}</a>
        </Button>
      }
    >
      <div dir={dir} className="font-arabic mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border bg-card p-4">
          <h2 className="mb-3 flex items-center gap-2 font-semibold">
            <Flag className="size-4 text-amber-600" aria-hidden /> {t("history.reports")}
            {reports.data && <span className="text-muted-foreground">({num(reports.data.length)})</span>}
          </h2>
          {reports.isLoading && <Skeleton className="h-24 w-full" />}
          {reports.data?.length === 0 && <p className="text-sm text-muted-foreground">{t("review.noReports")}</p>}
          <ul className="space-y-3">
            {reports.data?.map((r) => (
              <li key={r.id} className="rounded-xl bg-muted/50 p-3 text-sm">
                {ruling(r.doc_id, r.decision_no, r.category)}
                {r.quote && <p dir="rtl" className="mt-1">«{r.quote}»</p>}
                {r.note && <p className="mt-1 text-muted-foreground">{r.note}</p>}
                <p className="mt-1 text-xs text-muted-foreground">{r.reporter} · {when(r.created_at)}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-2xl border bg-card p-4">
          <h2 className="mb-3 flex items-center gap-2 font-semibold">
            <FileText className="size-4" aria-hidden /> {t("history.drafts")}
            {drafts.data && <span className="text-muted-foreground">({num(drafts.data.length)})</span>}
          </h2>
          {drafts.isLoading && <Skeleton className="h-24 w-full" />}
          {drafts.data?.length === 0 && <p className="text-sm text-muted-foreground">{t("review.noDrafts")}</p>}
          <ul className="space-y-3">
            {drafts.data?.map((d) => (
              <li key={d.id} className="rounded-xl bg-muted/50 p-3 text-sm">
                {ruling(d.doc_id, d.decision_no, d.category)}
                <p className="mt-1">{label(d.action)} · <span className="text-muted-foreground">{summary(d.summary)}</span></p>
                <p className="mt-1 text-xs text-muted-foreground">{t("history.by")} {d.actor} · {when(d.created_at)}</p>
              </li>
            ))}
          </ul>
        </section>

        <p className="text-xs text-muted-foreground lg:col-span-2">
          {t("review.exportHint")}{" "}
          <code dir="ltr" className="rounded bg-muted px-1.5 py-0.5 font-mono">
            python -m anonymizer.assemble --edits edits.zip
          </code>
        </p>
      </div>
    </AppShell>
  );
}
