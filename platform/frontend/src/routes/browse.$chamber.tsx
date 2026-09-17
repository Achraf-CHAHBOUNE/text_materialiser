import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ChevronRight, FileText, Search, X } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { browseCities, browseRulings, browseYears } from "@/lib/api";
import { arabicNumber, chamberLabel, chamberStyle } from "@/lib/chambers";

const PAGE = 50;
const ALL = "الكل";

type SearchParams = { q?: string; year?: string; city?: string; page?: number };

export const Route = createFileRoute("/browse/$chamber")({
  validateSearch: (s: Record<string, unknown>): SearchParams => ({
    q: typeof s.q === "string" && s.q ? s.q : undefined,
    year: typeof s.year === "string" && s.year ? s.year : undefined,
    city: typeof s.city === "string" && s.city ? s.city : undefined,
    page: Number(s.page) > 1 ? Number(s.page) : undefined,
  }),
  component: ChamberListing,
});

function ChamberListing() {
  const { chamber } = Route.useParams();
  const { q, year, city, page = 1 } = Route.useSearch();
  const navigate = useNavigate({ from: "/browse/$chamber" });
  const [draft, setDraft] = useState(q ?? "");
  const filterChamber = chamber === ALL ? "" : chamber;
  const style = chamberStyle(chamber);

  const setSearch = (next: Partial<SearchParams>) =>
    navigate({ search: (old) => ({ ...old, page: undefined, ...next }) });

  const years = useQuery({
    queryKey: ["browse", "years", filterChamber],
    queryFn: () => browseYears(filterChamber),
  });
  const cities = useQuery({
    queryKey: ["browse", "cities", filterChamber],
    queryFn: () => browseCities(filterChamber),
  });
  const rulings = useQuery({
    queryKey: ["browse", "rulings", filterChamber, year, city, q, page],
    queryFn: () =>
      browseRulings({ chamber: filterChamber, year, city, q, limit: PAGE, offset: (page - 1) * PAGE }),
    placeholderData: keepPreviousData,
  });

  const total = rulings.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <AppShell>
      <div dir="rtl" className="font-arabic mx-auto w-full max-w-6xl">
        <nav className="mb-3 flex items-center gap-1 text-sm text-muted-foreground">
          <Link to="/browse" className="hover:text-foreground">الاجتهادات القضائية</Link>
          <ChevronRight className="size-4 rotate-180" aria-hidden />
          <span className="text-foreground">{chamber === ALL ? "كل الغرف" : chamberLabel(chamber)}</span>
        </nav>

        <div className={`flex flex-col gap-3 rounded-2xl px-5 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between ${style.solid}`}>
          <div>
            <h1 className="text-lg font-semibold sm:text-xl">
              {chamber === ALL ? "كل الغرف" : chamberLabel(chamber)}
            </h1>
            <p className="mt-0.5 text-xs opacity-90">
              محكمة النقض — {arabicNumber(total)} قرار
            </p>
          </div>
          <form
            className="relative sm:w-72"
            onSubmit={(e) => { e.preventDefault(); setSearch({ q: draft.trim() || undefined }); }}
          >
            <Search className="absolute end-3 top-1/2 size-4 -translate-y-1/2 opacity-70" aria-hidden />
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="ابحث برقم القرار أو بكلمة من نصه…"
              aria-label="بحث"
              className="h-10 border-white/30 bg-white/15 pe-10 text-white placeholder:text-white/70"
            />
          </form>
        </div>

        {/* Years, as chips: the reference portal uses a dropdown, but the whole range
            fits here and one click is quicker than opening a menu. */}
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <Chip active={!year} onClick={() => setSearch({ year: undefined })}>كل السنوات</Chip>
          {(years.data ?? []).map((y) => (
            <Chip key={y.year} active={year === y.year} onClick={() => setSearch({ year: y.year })}>
              {y.year} <span className="opacity-60">({arabicNumber(y.count)})</span>
            </Chip>
          ))}
        </div>

        {(q || city || year) && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">التصفية:</span>
            {q && <Pill onClear={() => { setDraft(""); setSearch({ q: undefined }); }}>بحث: {q}</Pill>}
            {year && <Pill onClear={() => setSearch({ year: undefined })}>السنة: {year}</Pill>}
            {city && <Pill onClear={() => setSearch({ city: undefined })}>المدينة: {city}</Pill>}
          </div>
        )}

        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_15rem]">
          <div className="min-w-0">
            {rulings.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-11 w-full rounded-lg" />)}
              </div>
            ) : total === 0 ? (
              <p className="rounded-2xl border bg-card px-5 py-12 text-center text-sm text-muted-foreground">
                لا توجد قرارات مطابقة.
              </p>
            ) : (
              <RulingTable rows={rulings.data?.items ?? []} chamber={chamber} />
            )}

            {pages > 1 && (
              <div className="mt-4 flex items-center justify-center gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1}
                        onClick={() => navigate({ search: (o) => ({ ...o, page: page - 1 }) })}>
                  السابق
                </Button>
                <span className="text-sm text-muted-foreground">
                  صفحة {arabicNumber(page)} من {arabicNumber(pages)}
                </span>
                <Button variant="outline" size="sm" disabled={page >= pages}
                        onClick={() => navigate({ search: (o) => ({ ...o, page: page + 1 }) })}>
                  التالي
                </Button>
              </div>
            )}
          </div>

          {/* Cities are ours, not on the reference site: filtering by the court the
              appeal came from is the question a lawyer actually asks. */}
          <aside className="hidden lg:block">
            <div className="rounded-2xl border bg-card p-3">
              <h2 className="px-1 pb-2 text-sm font-semibold">المدينة</h2>
              <ul className="max-h-[28rem] space-y-0.5 overflow-auto pe-1">
                <li>
                  <FilterRow active={!city} onClick={() => setSearch({ city: undefined })} label="الكل" />
                </li>
                {(cities.data ?? []).map((c) => (
                  <li key={c.city}>
                    <FilterRow
                      active={city === c.city}
                      onClick={() => setSearch({ city: c.city })}
                      label={c.city}
                      count={c.count}
                    />
                  </li>
                ))}
              </ul>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}

function RulingTable({ rows, chamber }: { rows: import("@/lib/api").ListingRow[]; chamber: string }) {
  const style = chamberStyle(chamber);
  return (
    <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] border-collapse text-sm">
          <thead>
            <tr className="text-white">
              <Th className="bg-rose-600">رقم القرار</Th>
              <Th className="bg-violet-600">تاريخ القرار</Th>
              <Th className="bg-teal-600">المدينة</Th>
              <Th className="bg-amber-600">الغرفة</Th>
              <th className="w-10 bg-slate-700" aria-label="فتح" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={r.doc_id}
                className={`border-t transition-colors hover:bg-accent ${i % 2 ? "" : style.soft}`}
              >
                <td className="px-3 py-2.5 font-semibold tabular-nums">{r.decision_no || "—"}</td>
                <td className="px-3 py-2.5 tabular-nums text-muted-foreground">{r.date || "—"}</td>
                <td className="px-3 py-2.5">{r.city || <span className="text-muted-foreground">—</span>}</td>
                <td className={`px-3 py-2.5 ${chamberStyle(r.chamber).text}`}>{chamberLabel(r.chamber)}</td>
                <td className="px-2 py-2.5">
                  <Link
                    to="/ruling/$docId"
                    params={{ docId: r.doc_id }}
                    aria-label={`فتح القرار ${r.decision_no}`}
                    className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                  >
                    <FileText className="size-4" aria-hidden />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <th className={`px-3 py-2.5 text-start text-xs font-semibold ${className}`}>{children}</th>;
}

function Chip({ active, onClick, children }: {
  active?: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs transition-colors ${
        active ? "border-transparent bg-primary text-primary-foreground" : "hover:bg-accent"
      }`}
    >
      {children}
    </button>
  );
}

function Pill({ children, onClear }: { children: React.ReactNode; onClear: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1">
      {children}
      <button type="button" onClick={onClear} aria-label="إزالة" className="hover:text-destructive">
        <X className="size-3" aria-hidden />
      </button>
    </span>
  );
}

function FilterRow({ active, onClick, label, count }: {
  active?: boolean; onClick: () => void; label: string; count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-sm transition-colors ${
        active ? "bg-primary text-primary-foreground" : "hover:bg-accent"
      }`}
    >
      <span>{label}</span>
      {count !== undefined && <span className="text-xs opacity-70">{arabicNumber(count)}</span>}
    </button>
  );
}
