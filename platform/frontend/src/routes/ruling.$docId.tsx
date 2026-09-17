import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight, Download, Printer } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { decisionFileUrl, getDecision } from "@/lib/api";
import { chamberLabel, chamberStyle } from "@/lib/chambers";

export const Route = createFileRoute("/ruling/$docId")({
  component: RulingPage,
});

function RulingPage() {
  const { docId } = Route.useParams();
  const ruling = useQuery({ queryKey: ["ruling", docId], queryFn: () => getDecision(docId) });
  const d = ruling.data;
  const style = chamberStyle(d?.category ?? "");

  return (
    <AppShell>
      <div dir="rtl" className="font-arabic mx-auto w-full max-w-4xl">
        <nav className="mb-3 flex items-center gap-1 text-sm text-muted-foreground">
          <Link to="/browse" className="hover:text-foreground">الاجتهادات القضائية</Link>
          {d && (
            <>
              <ChevronRight className="size-4 rotate-180" aria-hidden />
              <Link to="/browse/$chamber" params={{ chamber: d.category }} className="hover:text-foreground">
                {chamberLabel(d.category)}
              </Link>
            </>
          )}
        </nav>

        {ruling.isLoading && <Skeleton className="h-40 w-full rounded-2xl" />}
        {ruling.error && (
          <p className="rounded-2xl border bg-card px-5 py-10 text-center text-sm text-destructive">
            تعذّر فتح القرار. قد يكون غير منشور.
          </p>
        )}

        {d && (
          <>
            <header className={`rounded-2xl px-5 py-4 shadow-sm ${style.solid}`}>
              <h1 className="text-lg font-semibold sm:text-xl">
                {d.court || "محكمة النقض"} — قرار عدد {d.decision_no || "—"}
              </h1>
              <p className="mt-0.5 text-xs opacity-90">
                {chamberLabel(d.category)} · {d.date || "بدون تاريخ"}
                {d.city ? ` · ${d.city}` : ""}
              </p>
            </header>

            <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Field label="رقم القرار" value={d.decision_no} />
              <Field label="تاريخ القرار" value={d.date} />
              <Field label="المدينة" value={d.city} />
              <Field label="رقم الملف" value={d.file_no} />
            </dl>

            <div className="mt-4 flex flex-wrap gap-2">
              <Button asChild size="sm">
                <a href={decisionFileUrl(d.doc_id)} download>
                  <Download className="size-4" aria-hidden /> تحميل الملف
                </a>
              </Button>
              <Button variant="outline" size="sm" onClick={() => window.print()}>
                <Printer className="size-4" aria-hidden /> طباعة
              </Button>
            </div>

            <article className="mt-4 whitespace-pre-wrap rounded-2xl border bg-card p-6 text-[15px] leading-8">
              {d.body_text || "لا يوجد نص متاح."}
            </article>

            <p className="mt-3 text-xs text-muted-foreground">
              أُزيلت البيانات الشخصية من هذا القرار آليًا وعُوّضت بالرمز XXXXXXX.
            </p>
          </>
        )}
      </div>
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
