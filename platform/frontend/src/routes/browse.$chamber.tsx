import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import {
  BellPlus,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  FileText,
  Search,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Fragment, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { FileNumber } from "@/components/FileNumber";
import { FilterMenu } from "@/components/FilterMenu";
import { Source } from "@/components/ruling/Headnote";
import { browseCities, browseRulings, browseThemes, browseYears, type ListingRow } from "@/lib/api";
import { createAlert } from "@/lib/api-biz";
import { chamberStyle } from "@/lib/chambers";
import { useI18n } from "@/lib/i18n";

const PAGE_SIZES = [25, 50, 100, 200];
const DEFAULT_PAGE = 50;
const ALL = "الكل";

type SearchParams = {
  q?: string | undefined;
  year?: string | undefined;
  city?: string | undefined;
  theme?: string | undefined;
  page?: number | undefined;
  size?: number | undefined;
};

export const Route = createFileRoute("/browse/$chamber")({
  validateSearch: (s: Record<string, unknown>): SearchParams => ({
    q: typeof s["q"] === "string" && s["q"] ? (s["q"] as string) : undefined,
    year: typeof s["year"] === "string" && s["year"] ? (s["year"] as string) : undefined,
    city: typeof s["city"] === "string" && s["city"] ? (s["city"] as string) : undefined,
    theme: typeof s["theme"] === "string" && s["theme"] ? (s["theme"] as string) : undefined,
    page: Number(s["page"]) > 1 ? Number(s["page"]) : undefined,
    size: PAGE_SIZES.includes(Number(s["size"])) ? Number(s["size"]) : undefined,
  }),
  component: ChamberListing,
});

function ChamberListing() {
  const { chamber } = Route.useParams();
  const { q, year, city, theme, page = 1, size } = Route.useSearch();
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

  const themes = useQuery({
    queryKey: ["browse", "themes", filterChamber, lang],
    queryFn: () => browseThemes(filterChamber, lang),
  });

  const years = useQuery({
    queryKey: ["browse", "years", filterChamber],
    queryFn: () => browseYears(filterChamber),
  });
  const cities = useQuery({
    queryKey: ["browse", "cities", filterChamber],
    queryFn: () => browseCities(filterChamber),
  });
  const listQuery = (p: number) => ({
    queryKey: ["browse", "rulings", filterChamber, year, city, theme, q, p, perPage, lang] as const,
    queryFn: () =>
      browseRulings({
        chamber: filterChamber,
        year,
        city,
        theme,
        q,
        limit: perPage,
        offset: (p - 1) * perPage,
        lang,
      }),
  });
  const rulings = useQuery({ ...listQuery(page), placeholderData: keepPreviousData });

  const total = rulings.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / perPage));

  // Fetch the next page while this one is being read, so "next" lands instantly.
  useEffect(() => {
    if (page < pages) queryClient.prefetchQuery(listQuery(page + 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pages, filterChamber, year, city, theme, q, perPage, lang]);

  return (
    <AppShell>
      <div dir={dir} className="font-arabic mx-auto w-full max-w-6xl">
        <nav className="mb-3 flex items-center gap-1 text-sm text-muted-foreground">
          <Link to="/browse" className="hover:text-foreground">
            {t("browse.title")}
          </Link>
          <ChevronRight className={`size-4 ${lang === "ar" ? "rotate-180" : ""}`} aria-hidden />
          <span className="text-foreground">{title}</span>
        </nav>

        <div
          className={`flex flex-col gap-3 rounded-2xl px-5 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between ${style.solid}`}
        >
          <div>
            <h1 className="text-lg font-semibold sm:text-xl">{title}</h1>
            <p className="mt-0.5 text-xs opacity-90">
              {t("court.cassation")} — {num(total)} {t("browse.rulingsCount")}
            </p>
          </div>
          <form
            className="relative sm:w-72"
            onSubmit={(e) => {
              e.preventDefault();
              setSearch({ q: draft.trim() || undefined });
            }}
          >
            <Search
              className="absolute end-3 top-1/2 size-4 -translate-y-1/2 opacity-70"
              aria-hidden
            />
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t("listing.search")}
              aria-label={t("listing.search")}
              className="h-10 border-white/30 bg-white/15 pe-10 text-white placeholder:text-white/70"
            />
          </form>
        </div>

        {/* One row of menus rather than every value laid out at once: 27 years, 70
            cities and 250 subjects between them, which used to push the rulings off
            the first screen. */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <FilterMenu
            label={t("listing.theme")}
            value={theme}
            allLabel={t("listing.allThemes")}
            searchPlaceholder={t("listing.findTheme")}
            width="22rem"
            options={(themes.data ?? []).map((x) => ({
              key: x.key,
              label: x.label,
              count: x.count,
            }))}
            onChange={(k) => setSearch({ theme: k })}
          />
          <FilterMenu
            label={t("listing.filterYear")}
            value={year}
            allLabel={t("listing.allYears")}
            searchPlaceholder={t("listing.findYear")}
            width="13rem"
            options={(years.data ?? []).map((y) => ({
              key: y.year,
              label: num(y.year),
              count: y.count,
            }))}
            onChange={(k) => setSearch({ year: k })}
          />
          <FilterMenu
            label={t("listing.city")}
            value={city}
            allLabel={t("listing.all")}
            searchPlaceholder={t("listing.findCity")}
            width="16rem"
            options={(cities.data ?? []).map((c) => ({
              key: c.city,
              label: cityName(c.city),
              count: c.count,
            }))}
            onChange={(k) => setSearch({ city: k })}
          />
          {(q || theme || filterChamber) && (
            <Button
              variant="outline"
              size="sm"
              className="h-10"
              onClick={() =>
                createAlert({
                  query: q ?? "",
                  chamber: filterChamber,
                  theme: theme ?? "",
                  year: year ?? "",
                  city: city ?? "",
                  lang,
                  name: [
                    q,
                    theme ? themes.data?.find((x) => x.key === theme)?.label : "",
                    filterChamber ? chamberName(filterChamber) : "",
                  ]
                    .filter(Boolean)
                    .join(" · "),
                })
                  .then(() => toast.success(t("alert.created")))
                  .catch((e) => toast.error(e instanceof Error ? e.message : t("adm.failed")))
              }
            >
              <BellPlus className="size-4" />
              {t("alert.create")}
            </Button>
          )}
          <p className="ms-auto hidden text-xs text-muted-foreground sm:block">
            {t("listing.themeNote")}
          </p>
        </div>

        {q && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">{t("listing.filters")}</span>
            <Pill
              onClear={() => {
                setDraft("");
                setSearch({ q: undefined });
              }}
              label={t("listing.clear")}
            >
              {t("listing.filterSearch")}: {q}
            </Pill>
          </div>
        )}

        <div className="mt-4">
          <div className="min-w-0">
            {rulings.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-11 w-full rounded-lg" />
                ))}
              </div>
            ) : total === 0 ? (
              <p className="rounded-2xl border bg-card px-5 py-12 text-center text-sm text-muted-foreground">
                {t("listing.none")}
              </p>
            ) : (
              <RulingTable rows={rulings.data?.items ?? []} chamber={chamber} q={q} />
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
        </div>
      </div>
    </AppShell>
  );
}

function RulingTable({
  rows,
  chamber,
  q,
}: {
  rows: ListingRow[];
  chamber: string;
  q?: string | undefined;
}) {
  const { t, num, chamber: chamberName, city: cityName } = useI18n();
  const style = chamberStyle(chamber);
  return (
    <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[48rem] border-collapse text-sm">
          <thead>
            <tr className="text-white">
              <Th className="bg-sky-700 whitespace-nowrap">{t("col.fileNo")}</Th>
              <Th className="bg-rose-600 whitespace-nowrap">{t("col.number")}</Th>
              <Th className="bg-violet-600 whitespace-nowrap">{t("col.date")}</Th>
              <Th className="bg-emerald-700">{t("col.keys")}</Th>
              <Th className="bg-teal-600 whitespace-nowrap">{t("col.city")}</Th>
              <Th className="bg-amber-600 whitespace-nowrap">{t("col.chamber")}</Th>
              <th className="w-10 bg-slate-700" aria-label={t("listing.open")} />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={r.doc_id}
                className={`border-t align-top transition-colors hover:bg-accent ${i % 2 ? "" : style.soft}`}
              >
                <td className="px-3 py-2.5 tabular-nums text-muted-foreground whitespace-nowrap">
                  <FileNumber value={r.file_no} />
                </td>
                <td className="px-3 py-2.5 font-semibold tabular-nums whitespace-nowrap">
                  {r.decision_no ? num(r.decision_no) : "—"}
                </td>
                <td className="px-3 py-2.5 tabular-nums text-muted-foreground whitespace-nowrap">
                  {r.date ? num(r.date) : "—"}
                </td>
                <td className="max-w-xl px-3 py-2.5">
                  <KeysCell row={r} q={q} />
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  {r.city ? cityName(r.city) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className={`px-3 py-2.5 whitespace-nowrap ${chamberStyle(r.chamber).text}`}>
                  {chamberName(r.chamber)}
                </td>
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

/** What the ruling is about, in the one column the portal gives it.
 *
 *  Whichever of the three the ruling offers: the court's keyword chain and its rule,
 *  or - for the rulings that print neither - a subject and a summary written for us,
 *  marked as such. Rows with nothing at all say so rather than sitting empty, which
 *  would read as a page that failed to load.
 */
function KeysCell({ row, q }: { row: ListingRow; q?: string | undefined }) {
  const { t, lang } = useI18n();
  if (lang === "fr") return <KeysCellFr row={row} q={q} />;
  const heading = row.keywords || row.theme;
  const summary = row.rule || row.abstract;
  const fromCourt = Boolean(row.rule);
  if (!heading && !summary) {
    return <span className="text-xs text-muted-foreground">{t("listing.noTheme")}</span>;
  }
  return (
    <div className="space-y-1 leading-relaxed">
      {heading && (
        <p className="font-medium">
          <Highlight text={heading} q={q} />
          {/* one badge for the cell: on the heading only when no summary carries it */}
          {!summary && row.theme_source === "model" && <Source court={false} />}
        </p>
      )}
      {summary && (
        <>
          <p className="line-clamp-3 text-xs text-muted-foreground">
            <Highlight text={summary} q={q} />
          </p>
          {/* outside the clamp on purpose: inside it, a long summary pushed the badge
              past the cut and a machine-written one would read as the court's */}
          {!fromCourt && <Source court={false} />}
        </>
      )}
    </div>
  );
}

/** The same cell in French. Everything French here is a machine translation, and says
 *  so; a part with no French yet is shown in Arabic, set right to left, rather than
 *  left out -- an empty cell would read as a ruling about nothing. */
function KeysCellFr({ row, q }: { row: ListingRow; q?: string | undefined }) {
  const { t } = useI18n();
  const headingFr = row.keywords_fr || row.theme_fr;
  const headingAr = row.keywords || row.theme;
  const summaryFr = row.abstract_fr;
  const summaryAr = row.rule || row.abstract;
  if (!headingFr && !headingAr && !summaryFr && !summaryAr) {
    return <span className="text-xs text-muted-foreground">{t("listing.noTheme")}</span>;
  }
  return (
    <div className="space-y-1 leading-relaxed">
      {headingFr ? (
        <p className="font-medium">
          <Highlight text={headingFr} q={q} />
        </p>
      ) : headingAr ? (
        <p className="font-medium font-arabic" dir="rtl" lang="ar">
          {headingAr}
        </p>
      ) : null}
      {summaryFr ? (
        <>
          <p className="line-clamp-3 text-xs text-muted-foreground">
            <Highlight text={summaryFr} q={q} />
          </p>
          <span className="inline-block rounded bg-muted px-1.5 py-0.5 text-[0.65rem] text-muted-foreground">
            {row.abstract_fr_of === "rule" ? t("fr.ruleTranslated") : t("fr.machineSummary")}
          </span>
        </>
      ) : summaryAr ? (
        <>
          <p className="line-clamp-3 text-xs text-muted-foreground font-arabic" dir="rtl" lang="ar">
            {summaryAr}
          </p>
          <span className="inline-block rounded bg-muted px-1.5 py-0.5 text-[0.65rem] text-muted-foreground">
            {t("fr.notTranslated")}
          </span>
        </>
      ) : null}
    </div>
  );
}

/** Marks what the reader searched for, the way the court portal does. Matching is on
 *  the raw text rather than the normalised form the server searches with, so a word
 *  written with different Arabic spellings may match a row without being marked in
 *  it: a missing highlight is better than one sitting on the wrong letters. */
function Highlight({ text, q }: { text: string; q?: string | undefined }) {
  const needle = (q ?? "").trim();
  if (needle.length < 2 || !text.includes(needle)) return <>{text}</>;
  const parts = text.split(needle);
  return (
    <>
      {parts.map((part, i) => (
        <Fragment key={i}>
          {part}
          {i < parts.length - 1 && (
            <mark className="rounded-sm bg-yellow-200 px-0.5 text-foreground dark:bg-yellow-500/40">
              {needle}
            </mark>
          )}
        </Fragment>
      ))}
    </>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={`px-3 py-2.5 text-start text-xs font-semibold ${className}`}>{children}</th>
  );
}

function Pill({
  children,
  onClear,
  label,
}: {
  children: React.ReactNode;
  onClear: () => void;
  label: string;
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

/** Page numbers with a sliding window, both ends always reachable, and a page size. */
function Pager({
  page,
  pages,
  total,
  perPage,
  onPage,
  onSize,
}: {
  page: number;
  pages: number;
  total: number;
  perPage: number;
  onPage: (p: number) => void;
  onSize: (n: number) => void;
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
        {t("listing.showing")} {num(from)} {t("listing.to")} {num(to)} {t("listing.results")}{" "}
        {num(total)}
      </p>
      {pages > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("listing.first")}
            disabled={page <= 1}
            onClick={() => onPage(1)}
            className="size-9"
          >
            <ChevronsRight className="size-4 rtl:hidden" aria-hidden />
            <ChevronsLeft className="hidden size-4 rtl:block" aria-hidden />
          </Button>
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
            {t("listing.prev")}
          </Button>
          {numbers.map((n, i) =>
            n === "gap" ? (
              <span key={`gap${i}`} className="px-1 text-muted-foreground">
                …
              </span>
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
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => onPage(page + 1)}
          >
            {t("listing.next")}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("listing.last")}
            disabled={page >= pages}
            onClick={() => onPage(pages)}
            className="size-9"
          >
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
