import type { Decision } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** The subject, and the rule or the summary, above the ruling's text.
 *
 *  Two things can appear here and they must never be mistaken for each other. القاعدة
 *  is the court's own wording, printed on the ruling; الملخص is written for us by a
 *  model, for the rulings - more than half of them - that print no rule at all. The
 *  court's version is shown whenever it exists, the generated one only otherwise, and
 *  each is labelled on its own line rather than by colour alone, so the distinction
 *  survives a printout and a screen reader.
 */
export function Headnote({ d }: { d: Decision }) {
  const { t } = useI18n();
  const keywords = d.keywords ?? "";
  const rule = d.rule ?? "";
  const abstract = d.abstract ?? "";
  const summary = rule || abstract;
  const fromCourt = Boolean(rule);
  if (!keywords && !d.theme && !summary) return null;

  const tone = fromCourt
    ? "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/60 dark:bg-emerald-950/30"
    : "border-sky-200 bg-sky-50/60 dark:border-sky-900/60 dark:bg-sky-950/30";
  const heading = fromCourt
    ? "text-emerald-800 dark:text-emerald-300"
    : "text-sky-800 dark:text-sky-300";

  return (
    <section aria-label={t("ruling.headnote")} className={`mt-4 rounded-xl border p-4 ${tone}`}>
      {(keywords || d.theme) && (
        <>
          <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
            {keywords ? t("ruling.keywords") : t("listing.theme")}
            <Source court={d.theme_source !== "model"} />
          </h2>
          <p className="mt-1 font-medium leading-relaxed">{keywords || d.theme}</p>
        </>
      )}
      {summary && (
        <>
          <h2 className={`mt-3 text-xs font-semibold uppercase tracking-wide ${heading}`}>
            {fromCourt ? t("ruling.rule") : t("ruling.abstract")}
            <Source court={fromCourt} />
          </h2>
          <p className="mt-1 leading-relaxed text-muted-foreground">{summary}</p>
        </>
      )}
      <p className="mt-3 text-[11px] text-muted-foreground">
        {fromCourt ? t("ruling.headnoteNote") : t("ruling.abstractNote")}
      </p>
    </section>
  );
}

/** Says in words, not only in colour, whose wording this is. */
export function Source({ court }: { court: boolean }) {
  const { t } = useI18n();
  return (
    <span
      className={`ms-2 rounded px-1.5 py-0.5 text-[10px] font-normal normal-case ${
        court
          ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/50 dark:text-emerald-100"
          : "bg-sky-100 text-sky-900 dark:bg-sky-900/50 dark:text-sky-100"
      }`}
    >
      {court ? t("source.court") : t("source.model")}
    </span>
  );
}
