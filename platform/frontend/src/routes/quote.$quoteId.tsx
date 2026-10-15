import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Printer } from "lucide-react";

import { day, money } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { quoteDetail } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/quote/$quoteId")({
  head: () => ({ meta: [{ title: "عرض سعر · Devis" }] }),
  component: QuotePage,
});

/** The quote as a printable page; the browser's "print to PDF" makes the file. */
function QuotePage() {
  const { quoteId } = Route.useParams();
  const { t, lang, dir, num, status } = useI18n();
  const q = useQuery({ queryKey: ["quote", quoteId], queryFn: () => quoteDetail(Number(quoteId)) });
  const d = q.data;
  if (q.isError) return <p className="p-10 text-center text-sm text-destructive">{t("ruling.error")}</p>;
  if (!d) return <p className="p-10 text-center text-sm text-muted-foreground">{t("adm.loading")}</p>;
  return (
    <div dir={dir} className="min-h-screen bg-muted/30 py-8 print:bg-white print:py-0">
      <div className="mx-auto mb-4 flex max-w-3xl justify-end print:hidden">
        <Button onClick={() => window.print()}><Printer className="size-4" />{t("ruling.print")}</Button>
      </div>
      <article className="mx-auto max-w-3xl rounded-2xl border bg-white p-10 text-black shadow-soft print:rounded-none print:border-0 print:shadow-none">
        <header className="flex flex-wrap justify-between gap-6">
          <div>
            <p className="text-lg font-semibold">{d.seller.name || t("bill.sellerMissing")}</p>
            {d.seller.address && <p className="text-sm">{d.seller.address}</p>}
            {d.seller.ice && <p className="text-sm">ICE : {d.seller.ice}</p>}
          </div>
          <div className="text-end">
            <p className="text-2xl font-semibold">{t("quote.one")}</p>
            <p className="font-mono" dir="ltr">{d.number}</p>
            <p className="text-sm">{t("bill.issued")} : {day(d.issued_on)}</p>
            <p className="text-sm">{t("quote.validUntil")} : {day(d.valid_until)}</p>
          </div>
        </header>
        <section className="mt-8 rounded-lg bg-neutral-100 p-4 text-sm">
          <p className="text-xs text-neutral-500">{t("bill.billedTo")}</p>
          <p className="font-medium">{d.org?.name}</p>
          {d.org?.address && <p>{d.org.address}</p>}
          {d.org?.ice && <p>ICE : {d.org.ice}</p>}
        </section>
        <table className="mt-8 w-full text-sm">
          <thead><tr className="border-b text-xs text-neutral-500">
            <th className="py-2 text-start">{t("bill.description")}</th><th className="py-2 text-end">{t("quote.qty")}</th>
            <th className="py-2 text-end">{t("quote.unit")}</th><th className="py-2 text-end">{t("bill.amountHt")}</th>
          </tr></thead>
          <tbody>
            {d.lines.map((l, i) => (
              <tr key={i} className="border-b">
                <td className="py-2">{l.label}</td><td className="py-2 text-end tabular-nums">{num(l.qty)}</td>
                <td className="py-2 text-end tabular-nums">{money(l.unit_price, lang)}</td>
                <td className="py-2 text-end tabular-nums">{money(Math.round(l.qty * l.unit_price), lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="ms-auto mt-4 w-64 space-y-1 text-sm">
          <div className="flex justify-between"><dt>{t("bill.amountHt")}</dt><dd className="tabular-nums">{money(d.amount_ht, lang)}</dd></div>
          <div className="flex justify-between"><dt>{t("bill.vat")} ({d.vat_rate / 100} %)</dt><dd className="tabular-nums">{money(d.vat, lang)}</dd></div>
          <div className="flex justify-between border-t pt-1 font-semibold"><dt>{t("bill.total")}</dt><dd className="tabular-nums">{money(d.amount_ttc, lang)}</dd></div>
        </dl>
        {d.seats && <p className="mt-6 text-sm">{num(d.seats)} {t("pub.seats")} · {num(d.months)} {t("quote.months")}</p>}
        {d.notes && <p className="mt-4 whitespace-pre-wrap text-sm">{d.notes}</p>}
        <p className="mt-6 text-xs text-neutral-500">{t("adm.colStatus")} : {status(d.status)}</p>
      </article>
    </div>
  );
}
