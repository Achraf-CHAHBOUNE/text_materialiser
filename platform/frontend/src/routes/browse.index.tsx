import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ChevronLeft, Search } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { browseCourts, type CourtNode } from "@/lib/api";
import { arabicNumber, byChamberOrder, chamberLabel, chamberStyle } from "@/lib/chambers";

export const Route = createFileRoute("/browse/")({
  head: () => ({
    meta: [
      { title: "الاجتهادات القضائية — الاطلاع" },
      {
        name: "description",
        content: "تصفح الاجتهادات القضائية حسب المحكمة والغرفة والسنة.",
      },
    ],
  }),
  component: BrowsePage,
});

function BrowsePage() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const courts = useQuery({ queryKey: ["browse", "courts"], queryFn: browseCourts });

  const total = (courts.data ?? []).reduce((n, c) => n + c.total, 0);

  return (
    <AppShell>
      <div dir="rtl" className="font-arabic mx-auto w-full max-w-5xl">
        {/* The title bar of the reference portal: one strong band, search at its edge. */}
        <div className="grad-brand flex flex-col gap-3 rounded-2xl px-5 py-4 text-primary-foreground shadow-md sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-lg font-semibold sm:text-xl">الاجتهادات القضائية</h1>
            <p className="mt-0.5 text-xs opacity-90 sm:text-sm">
              محكمة النقض · المحكمة الدستورية · محاكم الاستئناف
            </p>
          </div>
          <form
            className="relative sm:w-72"
            onSubmit={(e) => {
              e.preventDefault();
              if (q.trim()) navigate({ to: "/browse/$chamber", params: { chamber: "الكل" }, search: { q: q.trim() } });
            }}
          >
            <Search className="absolute end-3 top-1/2 size-4 -translate-y-1/2 opacity-70" aria-hidden />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="البحث في نص القرارات…"
              aria-label="البحث في نص القرارات"
              className="h-10 border-white/30 bg-white/15 pe-10 text-primary-foreground placeholder:text-primary-foreground/70"
            />
          </form>
        </div>

        {total > 0 && (
          <p className="mt-3 text-center text-sm text-muted-foreground">
            {arabicNumber(total.toLocaleString("en-US").replace(/,/g, " "))} قرار متاح للاطلاع
          </p>
        )}

        {courts.isLoading && (
          <div className="mt-6 space-y-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 w-full rounded-2xl" />)}
          </div>
        )}

        {courts.error && (
          <p className="mt-8 text-center text-sm text-destructive">
            تعذّر تحميل القائمة. حدّث الصفحة أو أعد تسجيل الدخول.
          </p>
        )}

        <div className="mt-6 space-y-6">
          {(courts.data ?? []).map((court) => (
            <CourtSection key={court.court} court={court} />
          ))}
        </div>

        {courts.data?.length === 0 && (
          <p className="mt-10 text-center text-sm text-muted-foreground">
            لا توجد قرارات منشورة بعد.
          </p>
        )}
      </div>
    </AppShell>
  );
}

function CourtSection({ court }: { court: CourtNode }) {
  const chambers = [...court.chambers].sort(byChamberOrder);
  return (
    <section className="overflow-hidden rounded-2xl border bg-card shadow-sm">
      <h2 className="border-b bg-muted/40 px-5 py-3 text-center text-base font-semibold">
        {court.court}
      </h2>
      <ul>
        {chambers.map((c, i) => {
          const style = chamberStyle(c.chamber);
          return (
            <li key={c.chamber}>
              <Link
                to="/browse/$chamber"
                params={{ chamber: c.chamber }}
                className={`flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 ${style.ring} ${
                  i % 2 ? "bg-transparent" : style.soft
                }`}
              >
                <span className="flex items-center gap-2">
                  <span aria-hidden className={`size-1.5 rounded-full ${style.solid}`} />
                  <span className={`font-medium ${style.text}`}>{chamberLabel(c.chamber)}</span>
                </span>
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  {arabicNumber(c.count)} قرار
                  <ChevronLeft className="size-4" aria-hidden />
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
