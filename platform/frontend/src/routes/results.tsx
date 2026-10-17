import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { AlertCircle, LoaderCircle, Search, X } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { useI18n } from "@/lib/i18n";
import { ChamberBadge, LevelBadge } from "@/components/chips";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useStore } from "@/lib/app-store";
import { listDecisions, searchDecisions } from "@/lib/api";

export const Route = createFileRoute("/results")({
  head: () => ({ meta: [{ title: "القرارات · Décisions" }] }),
  component: Decisions,
});

function Decisions() {
  const { t, chamber: chamberName, level: levelName } = useI18n();
  const navigate = useNavigate();
  const { categories } = useStore();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [level, setLevel] = useState("all");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const categoryFilter = category === "all" ? "" : category;
  const levelFilter = level === "all" ? "" : level;
  const decisions = useQuery({
    queryKey: ["decisions", debouncedQuery, categoryFilter, levelFilter],
    queryFn: () =>
      debouncedQuery
        ? searchDecisions(debouncedQuery, { category: categoryFilter, level: levelFilter })
        : listDecisions({ category: categoryFilter, level: levelFilter, limit: 100 }),
    placeholderData: (previous) => previous,
  });
  const rows = decisions.data ?? [];
  const isSearching = query.trim() !== debouncedQuery || decisions.isFetching;

  return (
    <AppShell title={t("results.title")} description={t("results.subtitle")}>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px_160px]">
        <div className="relative">
          <Search
            className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("results.search")}
            aria-label={t("results.search")}
            className="h-11 ps-9 pe-10 font-ar"
          />
          {query && !isSearching && (
            <button
              type="button"
              onClick={() => setQuery("")}
              aria-label={t("common.clear")}
              className="absolute end-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" aria-hidden />
            </button>
          )}
          {isSearching && (
            <LoaderCircle
              className="absolute end-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-teal"
              aria-hidden
            />
          )}
        </div>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="h-11" aria-label={t("results.filterChamber")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("results.allChambers")}</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c} value={c} className="font-ar">
                {chamberName(c)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={level} onValueChange={setLevel}>
          <SelectTrigger className="h-11" aria-label={t("results.filterLevel")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("results.allLevels")}</SelectItem>
            {["ابتدائي", "استئناف", "نقض"].map((l) => (
              <SelectItem key={l} value={l} className="font-ar">
                {levelName(l)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-4 flex min-h-6 items-center justify-between gap-3" aria-live="polite">
        <p className="text-sm text-muted-foreground">
          {!decisions.isPending && !decisions.isError
            ? `${rows.length} ${t(rows.length === 1 ? "results.count" : "results.countPlural")}`
            : ""}
        </p>
        {(query || category !== "all" || level !== "all") && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setQuery("");
              setCategory("all");
              setLevel("all");
            }}
          >
            <X className="size-4" aria-hidden /> {t("common.clear")}
          </Button>
        )}
      </div>

      {decisions.isError && (
        <div
          role="alert"
          className="mt-4 flex flex-col items-center rounded-2xl border border-destructive/25 bg-destructive/5 px-5 py-8 text-center"
        >
          <AlertCircle className="size-6 text-destructive" aria-hidden />
          <p className="mt-2 text-sm text-destructive">{t("results.loadError")}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            onClick={() => void decisions.refetch()}
          >
            {t("results.retry")}
          </Button>
        </div>
      )}

      {!decisions.isError && (
        <div className="mt-2 overflow-auto rounded-2xl border bg-card shadow-soft">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b text-start text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-3 text-start">{t("col.number")}</th>
                <th className="px-4 py-3 text-start">{t("col.fileNo")}</th>
                <th className="px-4 py-3 text-start">{t("col.chamber")}</th>
                <th className="px-4 py-3 text-start">{t("col.level")}</th>
                <th className="px-4 py-3 text-start">{t("col.date")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {decisions.isPending &&
                Array.from({ length: 5 }, (_, i) => (
                  <tr key={i} aria-hidden className="border-b last:border-0">
                    <td colSpan={5} className="px-4 py-4">
                      <div className="skeleton h-5 rounded-lg" />
                    </td>
                  </tr>
                ))}
              {rows.map((d) => (
                <Fragment key={d.doc_id}>
                  <tr
                    tabIndex={0}
                    role="link"
                    onClick={() => navigate({ to: "/ruling/$docId", params: { docId: d.doc_id } })}
                    onKeyDown={(e) => {
                      if (e.key !== "Enter" && e.key !== " ") return;
                      e.preventDefault();
                      void navigate({ to: "/ruling/$docId", params: { docId: d.doc_id } });
                    }}
                    className="cursor-pointer transition-colors hover:bg-teal/6 focus:bg-teal/8"
                  >
                    <td className="px-4 py-4 font-medium">{d.decision_no || d.doc_id}</td>
                    <td className="px-4 py-4 font-ar">{d.file_no || "—"}</td>
                    <td className="px-4 py-4">
                      <ChamberBadge chamber={d.category} />
                    </td>
                    <td className="px-4 py-4">
                      <LevelBadge level={d.level} />
                    </td>
                    <td className="px-4 py-4 tabular-nums">{d.date || "—"}</td>
                  </tr>
                  {d.snippets?.length ? (
                  <tr className="border-b bg-muted/20 last:border-0">
                    <td colSpan={5} className="px-4 py-2 font-ar text-xs text-muted-foreground">
                      {d.snippets?.map((s, i) => (
                        <span key={i} className="me-3">
                          {s.split(/(«[^»]*»)/g).map((c, k) =>
                            c.startsWith("«") ? (
                              <mark key={k} className="rounded bg-teal/20 px-0.5 text-teal">
                                {c.slice(1, -1)}
                              </mark>
                            ) : (
                              <span key={k}>{c}</span>
                            ),
                          )}
                        </span>
                      ))}
                    </td>
                  </tr>
                  ) : null}
                </Fragment>
              ))}
              {!decisions.isPending && rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-14 text-center text-sm text-muted-foreground">
                    {query ? t("results.none") : t("results.noneYet")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </AppShell>
  );
}
