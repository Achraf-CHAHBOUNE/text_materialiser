import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ChevronRight, FileText, Search, X } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { browseCities, browseRulings, browseYears, type ListingRow } from "@/lib/api";
import { chamberStyle } from "@/lib/chambers";
import { useI18n } from "@/lib/i18n";

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
  const { t, dir, lang, num, chamber: chamberName, city: cityName } = useI18n();
  const [draft, setDraft] = useState(q ?? "");
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

            {pages > 1 && (
              <div className="mt-4 flex items-center justify-center gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1}
                        onClick={() => navigate({ search: (o) => ({ ...o, page: page - 1 }) })}>
                  {t("listing.prev")}
                </Button>
                <span className="text-sm text-muted-foreground">
                  {t("listing.page")} {num(page)} {t("listing.of")} {num(pages)}
                </span>
                <Button variant="outline" size="sm" disabled={page >= pages}
                        onClick={() => navigate({ search: (o) => ({ ...o, page: page + 1 }) })}>
                  {t("listing.next")}
                </Button>
              </div>
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
