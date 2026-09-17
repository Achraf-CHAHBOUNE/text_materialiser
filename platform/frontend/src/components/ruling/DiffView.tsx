import type { DiffHunk } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Changed stretches of a ruling: removed text struck through in red, added in green. */
export function DiffView({ hunks }: { hunks: DiffHunk[] }) {
  const { t, num } = useI18n();
  if (!hunks.length) {
    return <p className="py-6 text-center text-sm text-muted-foreground">{t("edit.noChange")}</p>;
  }
  return (
    <div className="space-y-3">
      {hunks.map((h, i) => (
        <div key={i} className="rounded-xl border bg-card">
          <div className="border-b px-3 py-1 text-xs text-muted-foreground">
            {t("edit.line")} {num(h.line)}
          </div>
          <p dir="rtl" className="whitespace-pre-wrap px-3 py-2 text-[15px] leading-8">
            {h.segments.map((s, k) =>
              s.op === "del" ? (
                <del key={k} className="rounded bg-destructive/15 text-destructive decoration-destructive/60">{s.text}</del>
              ) : s.op === "ins" ? (
                <ins key={k} className="rounded bg-emerald-500/15 text-emerald-700 no-underline dark:text-emerald-400">{s.text}</ins>
              ) : (
                <span key={k} className="text-muted-foreground">{s.text}</span>
              ),
            )}
          </p>
        </div>
      ))}
    </div>
  );
}
