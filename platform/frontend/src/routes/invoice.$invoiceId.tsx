import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Printer } from "lucide-react";

import { day, money } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { invoiceDetail } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/invoice/$invoiceId")({
  head: () => ({ meta: [{ title: "فاتورة · Facture" }] }),
  component: InvoicePage,
});

/** The invoice as a printable page: the browser's "print to PDF" makes the file. */
function InvoicePage() {
  const { invoiceId } = Route.useParams();
  const { t, lang, dir, status } = useI18n();
  const q = useQuery({
    queryKey: ["invoice", invoiceId],
    queryFn: () => invoiceDetail(Number(invoiceId)),
  });
  const i = q.data;
  if (q.isError)
    return <p className="p-10 text-center text-sm text-destructive">{t("ruling.error")}</p>;
  if (!i)
    return <p className="p-10 text-center text-sm text-muted-foreground">{t("adm.loading")}</p>;
  const pct = `${(i.vat_rate / 100).toLocaleString("fr-MA")} %`;
  return (
    <div dir={dir} className="min-h-screen bg-muted/30 py-8 print:bg-white print:py-0">
      <div className="mx-auto mb-4 flex max-w-3xl justify-end print:hidden">
        <Button onClick={() => window.print()}>
          <Printer className="size-4" />
          {t("ruling.print")}
        </Button>
      </div>
      <article className="mx-auto max-w-3xl rounded-2xl border bg-white p-10 text-black shadow-soft print:rounded-none print:border-0 print:shadow-none">
        <header className="flex flex-wrap justify-between gap-6">
          <div>
            <p className="text-lg font-semibold">{i.seller.name || t("bill.sellerMissing")}</p>
            {i.seller.address && <p className="text-sm">{i.seller.address}</p>}
            {i.seller.ice && <p className="text-sm">ICE : {i.seller.ice}</p>}
          </div>
          <div className="text-end">
            <p className="text-2xl font-semibold">{t("bill.invoice")}</p>
            <p className="font-mono" dir="ltr">
              {i.number}
            </p>
            <p className="text-sm">
              {t("bill.issued")} : {day(i.issued_on)}
            </p>
            <p className="text-sm">
              {t("bill.due")} : {day(i.due_on)}
            </p>
          </div>
        </header>
        <section className="mt-8 rounded-lg bg-neutral-100 p-4 text-sm">
          <p className="text-xs text-neutral-500">{t("bill.billedTo")}</p>
          <p className="font-medium">{i.org?.name}</p>
          {i.org?.address && <p>{i.org.address}</p>}
          {i.org?.city && <p>{i.org.city}</p>}
          {i.org?.ice && <p>ICE : {i.org.ice}</p>}
        </section>
        <table className="mt-8 w-full text-sm">
          <thead>
            <tr className="border-b text-start text-xs text-neutral-500">
              <th className="py-2 text-start">{t("bill.description")}</th>
              <th className="py-2 text-end">{t("bill.amountHt")}</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b">
              <td className="py-3">{i.description || "—"}</td>
              <td className="py-3 text-end tabular-nums">{money(i.amount_ht, lang)}</td>
            </tr>
          </tbody>
        </table>
        <dl className="ms-auto mt-4 w-64 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt>{t("bill.amountHt")}</dt>
            <dd className="tabular-nums">{money(i.amount_ht, lang)}</dd>
          </div>
          <div className="flex justify-between">
            <dt>
              {t("bill.vat")} ({pct})
            </dt>
            <dd className="tabular-nums">{money(i.vat, lang)}</dd>
          </div>
          <div className="flex justify-between border-t pt-1 font-semibold">
            <dt>{t("bill.total")}</dt>
            <dd className="tabular-nums">{money(i.amount_ttc, lang)}</dd>
          </div>
          {i.paid > 0 && (
            <div className="flex justify-between">
              <dt>{t("bill.paid")}</dt>
              <dd className="tabular-nums">{money(i.paid, lang)}</dd>
            </div>
          )}
          <div className="flex justify-between font-semibold">
            <dt>{t("bill.balance")}</dt>
            <dd className="tabular-nums">{money(i.balance, lang)}</dd>
          </div>
        </dl>
        <p className="mt-6 text-sm">
          {t("adm.colStatus")} : {status(i.status)}
        </p>
        {i.seller.rib && (
          <p className="mt-6 text-sm">
            {t("bill.payBy")} — RIB : <span dir="ltr">{i.seller.rib}</span>
          </p>
        )}
      </article>
    </div>
  );
}
