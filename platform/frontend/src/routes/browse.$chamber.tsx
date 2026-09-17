import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ChevronRight, ChevronsLeft, ChevronsRight, FileText, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { browseCities, browseRulings, browseYears, type ListingRow } from "@/lib/api";
import { chamberStyle } from "@/lib/chambers";
import { useI18n } from "@/lib/i18n";

const PAGE_SIZES = [25, 50, 100, 200];
const DEFAULT_PAGE = 50;
const ALL = "الكل";

type SearchParams = {
  q?: string | undefined;
  year?: string | undefined;
  city?: string | undefined;
  page?: number | undefined;
  size?: number | undefined;
};

export const Route = createFileRoute("/browse/$chamber")({
  validateSearch: (s: Record<string, unknown>): SearchParams => ({
    q: typeof s["q"] === "string" && s["q"] ? (s["q"] as string) : undefined,
    year: typeof s["year"] === "string" && s["year"] ? (s["year"] as string) : undefined,
    city: typeof s["city"] === "string" && s["city"] ? (s["city"] as string) : undefined,
    page: Number(s["page"]) > 1 ? Number(s["page"]) : undefined,
    size: PAGE_SIZES.includes(Number(s["size"])) ? Number(s["size"]) : undefined,
  }),
  component: ChamberListing,
});

function ChamberListing() {
  const { chamber } = Route.useParams();
  const { q, year, city, page = 1, size } = Route.useSearch();
  const navigate = useNavigate({ from: "/browse/$chamber" });
  const { t, dir, lang, num, chamber: chamberName, city: cityName } = useI18n();
  const [draft, setDraft] = useState(q ?? "");
  const queryClient = useQueryClient();
  const perPage = size ?? DEFAULT_PAGE;
  const filterChamber = chamber === ALL ? "" : chamber;
  const style = chamberStyle(chamber);
  const title = chamber === ALL ? t("listing.allChambers") : chamberName(chamber);

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
  const listQuery = (p: number) => ({
    queryKey: ["browse", "rulings", filterChamber, year, city, q, p, perPage] as const,
    queryFn: () => browseRulings({
      chamber: filterChamber, year, city, q, limit: perPage, offset: (p - 1) * perPage,
    }),
  });
  const rulings = useQuery({ ...listQuery(page), placeholderData: keepPreviousData });

  const total = rulings.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / perPage));

  // Fetch the next page while this one is being read, so "next" lands instantly.
  useEffect(() => {
    if (page < pages) queryClient.prefetchQuery(listQuery(page + 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pages, filterChamber, year, city, q, perPage]);

  return (
    <AppShell>
      <div dir={dir} className="font-arabic mx-auto w-full max-w-6xl">
        <nav className="mb-3 flex items-center gap-1 text-sm text-muted-foreground">
          <Link to="/browse" className="hover:text-foreground">{t("browse.title")}</Link>
          <ChevronRight className={`size-4 ${lang === "ar" ? "rotate-180" : ""}`} aria-hidden />
          <span className="text-foreground">{title}</span>
        </nav>

        <div className={`flex flex-col gap-3 rounded-2xl px-5 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between ${style.solid}`}>
          <div>
            <h1 className="text-lg font-semibold sm:text-xl">{title}</h1>
            <p className="mt-0.5 text-xs opacity-90">
              {t("court.cassation")} — {num(total)} {t("browse.rulingsCount")}
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
              placeholder={t("listing.search")}
              aria-label={t("listing.search")}
              className="h-10 border-white/30 bg-white/15 pe-10 text-white placeholder:text-white/70"
            />
          </form>
        </div>

        {/* Years as chips: the reference portal uses a dropdown, but the whole range
            fits here and one click is quicker than opening a menu. */}
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <Chip active={!year} onClick={() => setSearch({ year: undefined })}>{t("listing.allYears")}</Chip>
          {(years.data ?? []).map((y) => (
            <Chip key={y.year} active={year === y.year} onClick={() => setSearch({ year: y.year })}>
              {num(y.year)} <span className="opacity-60">({num(y.count)})</span>
            </Chip>
          ))}
        </div>

        {(q || city || year) && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">{t("listing.filters")}</span>
            {q && <Pill onClear={() => { setDraft(""); setSearch({ q: undefined }); }} label={t("listing.clear")}>{t("listing.filterSearch")}: {q}</Pill>}
            {year && <Pill onClear={() => setSearch({ year: undefined })} label={t("listing.clear")}>{t("listing.filterYear")}: {num(year)}</Pill>}
            {city && <Pill onClear={() => setSearch({ city: undefined })} label={t("listing.clear")}>{t("listing.filterCity")}: {cityName(city)}</Pill>}
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
                {t("listing.none")}
              </p>
            ) : (
              <RulingTable rows={rulings.data?.items ?? []} chamber={chamber} />
            )}

            {total > 0 && (
              <Pager
                page={page}
                pages={pages}
                total={total}
                perPage={perPage}
                onPage={(p) => navigate({ search: (o) => ({ ...o, page: p > 1 ? p : undefined }) })}
                onSize={(n) => navigate({ search: (o) => ({ ...o, page: undefined, size: n }) })}
              />
            )}
          </div>

          {/* Cities are ours, not on the reference site: filtering by the court the
              appeal came from is the question a lawyer actually asks. */}
          <aside className="hidden lg:block">
            <div className="rounded-2xl border bg-card p-3">
              <h2 className="px-1 pb-2 text-sm font-semibold">{t("listing.city")}</h2>
              <ul className="max-h-[28rem] space-y-0.5 overflow-auto pe-1">
                <li>
                  <FilterRow active={!city} onClick={() => setSearch({ city: undefined })} label={t("listing.all")} />
                </li>
                {(cities.data ?? []).map((c) => (
                  <li key={c.city}>
                    <FilterRow
                      active={city === c.city}
                      onClick={() => setSearch({ city: c.city })}
                      label={cityName(c.city)}
                      count={num(c.count)}
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

function RulingTable({ rows, chamber }: { rows: ListingRow[]; chamber: string }) {
  const { t, num, chamber: chamberName, city: cityName } = useI18n();
  const style = chamberStyle(chamber);
  return (
    <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] border-collapse text-sm">
          <thead>
            <tr className="text-white">
              <Th className="bg-rose-600">{t("col.number")}</Th>
              <Th className="bg-violet-600">{t("col.date")}</Th>
              <Th className="bg-teal-600">{t("col.city")}</Th>
              <Th className="bg-amber-600">{t("col.chamber")}</Th>
              <th className="w-10 bg-slate-700" aria-label={t("listing.open")} />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.doc_id} className={`border-t transition-colors hover:bg-accent ${i % 2 ? "" : style.soft}`}>
                <td className="px-3 py-2.5 font-semibold tabular-nums">{r.decision_no ? num(r.decision_no) : "—"}</td>
                <td className="px-3 py-2.5 tabular-nums text-muted-foreground">{r.date ? num(r.date) : "—"}</td>
                <td className="px-3 py-2.5">{r.city ? cityName(r.city) : <span className="text-muted-foreground">—</span>}</td>
                <td className={`px-3 py-2.5 ${chamberStyle(r.chamber).text}`}>{chamberName(r.chamber)}</td>
                <td className="px-2 py-2.5">
                  <Link
                    to="/ruling/$docId"
                    params={{ docId: r.doc_id }}
                    aria-label={`${t("listing.open")} ${r.decision_no}`}
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

function Pill({ children, onClear, label }: {
  children: React.ReactNode; onClear: () => void; label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1">
      {children}
      <button type="button" onClick={onClear} aria-label={label} className="hover:text-destructive">
        <X className="size-3" aria-hidden />
      </button>
    </span>
  );
}

function FilterRow({ active, onClick, label, count }: {
  active?: boolean; onClick: () => void; label: string; count?: string;
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
      {count !== undefined && <span className="text-xs opacity-70">{count}</span>}
    </button>
  );
}


/** Page numbers with a sliding window, both ends always reachable, and a page size. */
function Pager({ page, pages, total, perPage, onPage, onSize }: {
  page: number; pages: number; total: number; perPage: number;
  onPage: (p: number) => void; onSize: (n: number) => void;
}) {
  const { t, num } = useI18n();
  const from = (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);
  const span = 2;
  const numbers: (number | "gap")[] = [];
  for (let p = 1; p <= pages; p++) {
    if (p === 1 || p === pages || Math.abs(p - page) <= span) numbers.push(p);
    else if (numbers[numbers.length - 1] !== "gap") numbers.push("gap");
  }
  return (
    <div className="mt-4 flex flex-col items-center gap-3">
      <p className="text-xs text-muted-foreground">
        {t("listing.showing")} {num(from)} {t("listing.to")} {num(to)} {t("listing.results")} {num(total)}
      </p>
      {pages > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-1">
          <Button variant="ghost" size="icon" aria-label={t("listing.first")}
                  disabled={page <= 1} onClick={() => onPage(1)} className="size-9">
            <ChevronsRight className="size-4 rtl:hidden" aria-hidden />
            <ChevronsLeft className="hidden size-4 rtl:block" aria-hidden />
          </Button>
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
            {t("listing.prev")}
          </Button>
          {numbers.map((n, i) =>
            n === "gap" ? (
              <span key={`gap${i}`} className="px-1 text-muted-foreground">…</span>
            ) : (
              <Button
                key={n}
                variant={n === page ? "default" : "ghost"}
                size="sm"
                aria-current={n === page ? "page" : undefined}
                onClick={() => onPage(n)}
                className="min-w-9 tabular-nums"
              >
                {num(n)}
              </Button>
            ),
          )}
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
            {t("listing.next")}
          </Button>
          <Button variant="ghost" size="icon" aria-label={t("listing.last")}
                  disabled={page >= pages} onClick={() => onPage(pages)} className="size-9">
            <ChevronsLeft className="size-4 rtl:hidden" aria-hidden />
            <ChevronsRight className="hidden size-4 rtl:block" aria-hidden />
          </Button>
        </div>
      )}
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        {PAGE_SIZES.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onSize(n)}
            className={`rounded-md px-2 py-1 transition-colors ${
              n === perPage ? "bg-primary text-primary-foreground" : "hover:bg-accent"
            }`}
          >
            {num(n)}
          </button>
        ))}
        <span>{t("listing.perPage")}</span>
      </div>
    </div>
  );
}
