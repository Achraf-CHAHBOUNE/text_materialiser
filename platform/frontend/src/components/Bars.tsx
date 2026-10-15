// A small stacked bar chart by day: reads, downloads, searches. Plain divs, no library.
import { useI18n } from "@/lib/i18n";

export type DayRow = { day: string; view: number; download: number; search: number; users?: number };

const COLORS = { view: "bg-teal/80", download: "bg-sky-600/80", search: "bg-amber-500/80" };

export function Bars({ rows, days }: { rows: DayRow[]; days: number }) {
  const { t } = useI18n();
  // every day of the period, zero where nothing happened, so gaps show as gaps
  const map = new Map(rows.map((r) => [r.day, r]));
  const all: DayRow[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    all.push(map.get(d) ?? { day: d, view: 0, download: 0, search: 0 });
  }
  const top = Math.max(1, ...all.map((r) => r.view + r.download + r.search));
  return (
    <div>
      <div className="flex h-36 items-end gap-px" role="img" aria-label={t("trk.activity")}>
        {all.map((r) => (
          <div key={r.day} className="flex flex-1 flex-col-reverse" title={`${r.day} · ${t("trk.reads")} ${r.view} · ${t("trk.downloads")} ${r.download} · ${t("trk.searches")} ${r.search}${r.users !== undefined ? ` · ${t("trk.activeUsers")} ${r.users}` : ""}`}>
            {(["view", "download", "search"] as const).map((k) => (
              <div key={k} className={COLORS[k]} style={{ height: `${(r[k] / top) * 136}px` }} />
            ))}
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground">
        {(["view", "download", "search"] as const).map((k) => (
          <span key={k} className="flex items-center gap-1"><span className={`inline-block size-2.5 rounded-sm ${COLORS[k]}`} />
            {t(k === "view" ? "trk.reads" : k === "download" ? "trk.downloads" : "trk.searches")}</span>
        ))}
        <span className="ms-auto">{all[0]?.day} → {all[all.length - 1]?.day}</span>
      </div>
    </div>
  );
}
