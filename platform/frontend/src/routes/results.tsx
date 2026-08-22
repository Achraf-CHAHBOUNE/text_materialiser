import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ChamberBadge, LevelBadge } from "@/components/chips";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useStore } from "@/lib/app-store";
import { listDecisions, searchDecisions, type Decision } from "@/lib/api";

export const Route = createFileRoute("/results")({
  head: () => ({ meta: [{ title: "Decisions — القرارات" }] }),
  component: Decisions,
});

function Decisions() {
  const navigate = useNavigate();
  const { categories } = useStore();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [level, setLevel] = useState("all");
  const [rows, setRows] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(false);

  const filters = useMemo(
    () => ({ category: category === "all" ? "" : category, level: level === "all" ? "" : level }),
    [category, level],
  );

  useEffect(() => {
    setLoading(true);
    const p = query.trim()
      ? searchDecisions(query.trim(), filters)
      : listDecisions({ ...filters, limit: 100 });
    p.then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  }, [query, filters]);

  return (
    <AppShell title="Decisions" description="Browse and search published anonymized decisions">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px_160px]">
        <div className="relative">
          <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="بحث في القرارات…" aria-label="Search decisions" className="h-11 ps-9 font-ar" />
        </div>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="h-11" aria-label="Filter by chamber"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All chambers</SelectItem>
            {categories.map((c) => <SelectItem key={c} value={c} className="font-ar">{c}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={level} onValueChange={setLevel}>
          <SelectTrigger className="h-11" aria-label="Filter by level"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All levels</SelectItem>
            <SelectItem value="ابتدائي" className="font-ar">ابتدائي</SelectItem>
            <SelectItem value="استئناف" className="font-ar">استئناف</SelectItem>
            <SelectItem value="نقض" className="font-ar">نقض</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="mt-4 overflow-auto rounded-2xl border bg-card shadow-soft">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b text-start text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-3 text-start">رقم القرار</th>
              <th className="px-4 py-3 text-start">رقم الملف</th>
              <th className="px-4 py-3 text-start">الغرفة</th>
              <th className="px-4 py-3 text-start">المستوى</th>
              <th className="px-4 py-3 text-start">التاريخ</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((d) => (
              <tr key={d.doc_id} tabIndex={0} role="link"
                onClick={() => navigate({ to: "/cases/$caseId", params: { caseId: d.doc_id } })}
                onKeyDown={(e) => e.key === "Enter" && navigate({ to: "/cases/$caseId", params: { caseId: d.doc_id } })}
                className="cursor-pointer transition-colors odd:bg-muted/25 hover:bg-teal/6 focus:bg-teal/8">
                <td className="px-4 py-4 font-medium">{d.decision_no || d.doc_id}</td>
                <td className="px-4 py-4 font-ar">{d.file_no || "—"}</td>
                <td className="px-4 py-4"><ChamberBadge chamber={d.category} /></td>
                <td className="px-4 py-4"><LevelBadge level={d.level} /></td>
                <td className="px-4 py-4 tabular-nums">{d.date || "—"}</td>
              </tr>
            ))}
            {rows.map((d) =>
              d.snippets && d.snippets.length ? (
                <tr key={d.doc_id + "-snip"} className="bg-muted/10">
                  <td colSpan={5} className="px-4 py-2 font-ar text-xs text-muted-foreground">
                    {d.snippets.map((s, i) => (
                      <span key={i} className="me-3">
                        {s.split(/(«[^»]*»)/g).map((c, k) =>
                          c.startsWith("«") ? (
                            <mark key={k} className="rounded bg-teal/20 px-0.5 text-teal">{c.slice(1, -1)}</mark>
                          ) : (
                            <span key={k}>{c}</span>
                          ),
                        )}
                      </span>
                    ))}
                  </td>
                </tr>
              ) : null,
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-14 text-center text-sm text-muted-foreground">
                {query ? "لا نتائج مطابقة" : "لا قرارات منشورة بعد"}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
