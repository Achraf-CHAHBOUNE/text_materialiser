import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ExternalLink, GitBranch } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ChamberBadge, LevelBadge, Pill } from "@/components/chips";
import { Button } from "@/components/ui/button";
import { decisionFileUrl, getDecision, type Decision } from "@/lib/api";

export const Route = createFileRoute("/cases/$caseId")({
  loader: ({ params }) => ({ caseId: params.caseId }),
  head: ({ loaderData }) => ({
    meta: [{ title: loaderData ? `قرار ${loaderData.caseId} — القرارات` : "القرارات" }],
  }),
  component: DecisionDetail,
});

function DecisionDetail() {
  const { caseId } = Route.useParams();
  const navigate = useNavigate();
  const [d, setD] = useState<Decision | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    setError(false);
    getDecision(caseId).then(setD).catch(() => setError(true));
  }, [caseId]);

  if (error) {
    return (
      <AppShell title="Decision" description={caseId}>
        <div className="rounded-2xl border border-dashed bg-card p-10 text-center">
          <p className="text-sm font-medium">القرار غير متاح</p>
          <Link to="/results" className="mt-2 inline-block text-sm text-teal underline-offset-4 hover:underline">
            رجوع إلى القرارات
          </Link>
        </div>
      </AppShell>
    );
  }
  if (!d) return <AppShell title="Decision" description={caseId}><p className="text-sm text-muted-foreground">جارٍ التحميل…</p></AppShell>;

  return (
    <AppShell
      title={`قرار ${d.decision_no || d.doc_id}`}
      description={d.court || d.case_id}
      action={
        <div className="flex items-center gap-2">
          <Button asChild className="h-10">
            <a href={decisionFileUrl(d.doc_id)} target="_blank" rel="noreferrer">
              <ExternalLink className="size-4" />
              عرض الملف
            </a>
          </Button>
          <Button variant="outline" asChild className="h-10">
            <Link to="/results"><ArrowLeft className="size-4" />رجوع</Link>
          </Button>
        </div>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <ChamberBadge chamber={d.category} />
        <LevelBadge level={d.level} />
        {d.file_no && <Pill tone="muted"><span className="font-ar">ملف {d.file_no}</span></Pill>}
        {d.date && <Pill tone="muted">{d.date}</Pill>}
        {d.outcome && <Pill tone="teal"><span className="font-ar">{d.outcome}</span></Pill>}
      </div>

      {d.links && d.links.length > 0 && (
        <section className="mt-6 rounded-2xl border bg-card p-5 shadow-soft">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <GitBranch className="size-4 text-teal" /> قرارات مرتبطة
          </h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {d.links.map((l) => (
              <button key={l.to} type="button"
                onClick={() => navigate({ to: "/cases/$caseId", params: { caseId: l.to } })}
                className="rounded-xl border bg-background px-3 py-2 text-start text-sm transition-colors hover:border-teal/50 hover:bg-teal/5">
                <span className="font-ar">{l.role === "reviews" ? "يراجع" : "روجع من"} · {l.to}</span>
                <span className="ms-2 text-xs text-muted-foreground">{l.confidence}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="mt-6 rounded-2xl border bg-card shadow-soft">
        <header className="border-b px-5 py-4">
          <p className="text-sm font-semibold">النص المجهول</p>
          <p className="text-xs text-muted-foreground">
            الأسماء مستبدلة بـ <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">XXXXXXX</code>
          </p>
        </header>
        <div dir="rtl" className="max-h-[560px] overflow-auto px-5 py-6">
          <div className="font-ar space-y-3 text-[15px] leading-loose">
            {(d.body_text || "").split("\n").map((line, i) =>
              line.trim() ? (
                <p key={i}>
                  {line.split(/(XXXXXXX)/g).map((chunk, k) =>
                    chunk === "XXXXXXX" ? (
                      <mark key={k} className="rounded bg-teal/15 px-1 font-mono text-teal">XXXXXXX</mark>
                    ) : (
                      <span key={k}>{chunk}</span>
                    ),
                  )}
                </p>
              ) : null,
            )}
            {!d.body_text && <p className="text-center text-sm text-muted-foreground">لا معاينة نصية — استخدم زر عرض الملف.</p>}
          </div>
        </div>
      </section>
    </AppShell>
  );
}
