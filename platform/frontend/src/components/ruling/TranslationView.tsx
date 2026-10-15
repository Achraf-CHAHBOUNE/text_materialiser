import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Languages, Loader2, RotateCw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getTranslation, makeTranslation, type Translation } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export const translationKey = (docId: string) => ["translation", docId];
const key = translationKey;

/** The button. Asks for the French the first time; afterwards it is already there. */
export function TranslateButton({ docId, shown, onShow, onHide }: {
  docId: string;
  shown: boolean;
  onShow: () => void;
  onHide: () => void;
}) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const stored = useQuery({ queryKey: key(docId), queryFn: () => getTranslation(docId) });

  const ask = useMutation({
    mutationFn: () => makeTranslation(docId),
    onSuccess: (data) => {
      qc.setQueryData<Translation>(key(docId), data);
      onShow();
    },
    onError: (e) => toast.error(t("tr.failed"), {
      description: e instanceof Error ? e.message : undefined,
    }),
  });

  if (shown) {
    return (
      <Button variant="outline" size="sm" onClick={onHide}>
        <Languages className="size-4" aria-hidden /> {t("tr.hide")}
      </Button>
    );
  }
  const have = stored.data?.ready && !stored.data.stale;
  return (
    <Button variant="outline" size="sm" disabled={ask.isPending}
            onClick={() => (have ? onShow() : ask.mutate())}>
      {ask.isPending
        ? <Loader2 className="size-4 animate-spin" aria-hidden />
        : <Languages className="size-4" aria-hidden />}
      {ask.isPending ? t("tr.working") : t("tr.button")}
    </Button>
  );
}

/**
 * The ruling twice: the court's Arabic beside the machine's French, so a lawyer can
 * check one against the other. On a narrow screen they stack, Arabic first -- it is
 * the text that counts.
 */
export function TranslationView({ docId, arabic }: { docId: string; arabic: string }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const stored = useQuery({ queryKey: key(docId), queryFn: () => getTranslation(docId) });
  const again = useMutation({
    mutationFn: () => makeTranslation(docId),
    onSuccess: (data) => qc.setQueryData<Translation>(key(docId), data),
    onError: (e) => toast.error(t("tr.failed"), {
      description: e instanceof Error ? e.message : undefined,
    }),
  });

  const french = stored.data?.text ?? "";
  const stale = !!stored.data?.stale;

  return (
    <section className="mt-4">
      <p className="mb-2 rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-300">
        {t("tr.notice")}
      </p>

      {stale && (
        <div className="mb-2 flex flex-wrap items-center gap-2 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {t("tr.stale")}
          <Button size="sm" variant="outline" disabled={again.isPending} onClick={() => again.mutate()}>
            {again.isPending
              ? <Loader2 className="size-3.5 animate-spin" aria-hidden />
              : <RotateCw className="size-3.5" aria-hidden />}
            {t("tr.retry")}
          </Button>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <article dir="rtl" className="rounded-2xl border bg-card p-6 text-[15px] leading-8">
          <h2 className="mb-2 text-xs font-medium text-muted-foreground">{t("tr.original")}</h2>
          <div className="whitespace-pre-wrap">{arabic}</div>
        </article>
        <article dir="ltr" className="rounded-2xl border bg-card p-6 text-[15px] leading-7">
          <h2 className="mb-2 text-xs font-medium text-muted-foreground">{t("tr.french")}</h2>
          {french
            ? <div className="whitespace-pre-wrap font-sans">{french}</div>
            : <p className="text-sm text-muted-foreground">{t("tr.working")}</p>}
        </article>
      </div>
    </section>
  );
}

/**
 * The ruling on the French site: the French first, the Arabic one click away.
 *
 * The Arabic is still the ruling. The French says it is a machine translation at the
 * top, and the original is offered alone or side by side. With no French yet, the
 * Arabic is shown with a note, and the reader can ask for the translation.
 */
export function FrenchRuling({ docId, arabic, arabicView }: {
  docId: string;
  arabic: string;
  /** the Arabic text as the page normally shows it (selection, reporting, editing) */
  arabicView: ReactNode;
}) {
  const { t } = useI18n();
  const stored = useQuery({ queryKey: key(docId), queryFn: () => getTranslation(docId) });
  const [view, setView] = useState<"fr" | "ar" | "both">("fr");
  const have = !!stored.data?.ready && !stored.data.stale && !!stored.data.text;

  if (stored.isLoading) return <Skeleton className="mt-4 h-64 w-full rounded-2xl" />;

  if (!have) {
    return (
      <section className="mt-4">
        <div className="mb-2 flex flex-wrap items-center gap-2 rounded-xl bg-muted px-3 py-2 text-xs text-muted-foreground">
          {t("fr.textMissing")}
          <TranslateButton docId={docId} shown={false} onShow={() => setView("both")} onHide={() => undefined} />
        </div>
        {view === "both" && stored.data?.text ? <TranslationView docId={docId} arabic={arabic} /> : arabicView}
      </section>
    );
  }

  return (
    <section className="mt-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-300">
        <span>{t("tr.notice")}</span>
        <div className="flex gap-1" role="group" aria-label={t("fr.viewLabel")}>
          {(["fr", "ar", "both"] as const).map((v) => (
            <Button key={v} size="sm" variant={view === v ? "default" : "outline"}
                    aria-pressed={view === v} onClick={() => setView(v)} className="h-7 px-2 text-xs">
              {t(v === "fr" ? "fr.viewFr" : v === "ar" ? "fr.viewAr" : "fr.viewBoth")}
            </Button>
          ))}
        </div>
      </div>
      {view === "ar" ? arabicView : view === "both" ? <TranslationView docId={docId} arabic={arabic} /> : (
        <article dir="ltr" lang="fr" className="rounded-2xl border bg-card p-6 text-[15px] leading-7">
          <div className="whitespace-pre-wrap font-sans">{stored.data?.text}</div>
        </article>
      )}
    </section>
  );
}
