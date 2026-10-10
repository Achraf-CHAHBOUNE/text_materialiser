import { useI18n } from "@/lib/i18n";

/** A court file number, written left to right even on an Arabic page.
 *
 *  "1949 /6/13/2025" left to the surrounding direction is reordered by the browser
 *  into "6/13/2025/ 1949" - a different number, and the one a reader would copy down.
 *  The stray spaces come from the PDFs; they are closed up here rather than in the
 *  database, which keeps what the court filed.
 */
export function FileNumber({ value }: { value?: string }) {
  const { num } = useI18n();
  if (!value) return <span className="text-muted-foreground">—</span>;
  return <bdi dir="ltr">{num(value.replace(/\s*\/\s*/g, "/").trim())}</bdi>;
}
