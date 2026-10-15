import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Printer } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { day, money, Select } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cancelFeeNote, feeNote, payFeeNote } from "@/lib/api-practice";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/fee/$feeId")({
  head: () => ({ meta: [{ title: "مذكرة الأتعاب · Note d'honoraires" }] }),
  component: FeePage,
});

/** A firm's fee note to its client, printable; payments recorded from the same page. */
function FeePage() {
  const { feeId } = Route.useParams();
  const id = Number(feeId);
  const { t, lang, dir, status } = useI18n();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["fee", id], queryFn: () => feeNote(id) });
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("transfer");
  const [ref, setRef] = useState("");
  const done = (d: unknown) => { qc.setQueryData(["fee", id], d); void qc.invalidateQueries({ queryKey: ["fee-notes"] }); };
  const pay = useMutation({ mutationFn: () => payFeeNote(id, { amount: Math.round(parseFloat(amount.replace(",", ".") || "0") * 100), method, reference: ref }),
    onSuccess: (d) => { done(d); setAmount(""); setRef(""); toast.success(t("bill.paymentSaved")); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")) });
  const cancel = useMutation({ mutationFn: () => cancelFeeNote(id), onSuccess: done,
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")) });
  const f = q.data;
  if (q.isError) return <p className="p-10 text-center text-sm text-destructive">{t("ruling.error")}</p>;
  if (!f) return <p className="p-10 text-center text-sm text-muted-foreground">{t("adm.loading")}</p>;
  return (
    <div dir={dir} className="min-h-screen bg-muted/30 py-8 print:bg-white print:py-0">
      <div className="mx-auto mb-4 flex max-w-3xl flex-wrap items-center justify-end gap-2 print:hidden">
        {(f.status === "sent" || f.status === "overdue") && (
          <form className="flex flex-wrap gap-1" onSubmit={(e) => { e.preventDefault(); pay.mutate(); }}>
            <Input required value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={String(f.balance / 100)} className="h-9 w-28" dir="ltr" aria-label={t("bill.amount")} />
            <Select value={method} onChange={setMethod} className="h-9" label={t("bill.method")}
                    options={["transfer", "cheque", "cash", "card"].map((m) => ({ value: m, label: t(`pay.${m}` as "pay.cash") }))} />
            <Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder={t("bill.reference")} className="h-9 w-28" aria-label={t("bill.reference")} />
            <Button size="sm" type="submit" disabled={pay.isPending}>{t("bill.recordPayment")}</Button>
            {f.paid === 0 && <Button size="sm" type="button" variant="ghost" onClick={() => { if (window.confirm(t("bill.cancelConfirm"))) cancel.mutate(); }}>{t("team.cancel")}</Button>}
          </form>
        )}
        <Button onClick={() => window.print()}><Printer className="size-4" />{t("ruling.print")}</Button>
      </div>
      <article className="mx-auto max-w-3xl rounded-2xl border bg-white p-10 text-black shadow-soft print:rounded-none print:border-0 print:shadow-none">
        <header className="flex flex-wrap justify-between gap-6">
          <div>
            <p className="text-lg font-semibold">{f.firm?.name}</p>
            {f.firm?.address && <p className="text-sm">{f.firm.address}</p>}
            {f.firm?.city && <p className="text-sm">{f.firm.city}</p>}
            {f.firm?.ice && <p className="text-sm">ICE : {f.firm.ice}</p>}
            {f.firm?.phone && <p className="text-sm" dir="ltr">{f.firm.phone}</p>}
          </div>
          <div className="text-end">
            <p className="text-2xl font-semibold">{t("cab.feeNote")}</p>
            <p className="font-mono" dir="ltr">{f.number}</p>
            <p className="text-sm">{t("bill.issued")} : {day(f.issued_on)}</p>
            <p className="text-sm">{t("bill.due")} : {day(f.due_on)}</p>
          </div>
        </header>
        <section className="mt-8 grid gap-3 rounded-lg bg-neutral-100 p-4 text-sm sm:grid-cols-2">
          <div><p className="text-xs text-neutral-500">{t("bill.billedTo")}</p><p className="font-medium">{f.client?.full_name}</p>
            {f.client?.address && <p>{f.client.address}</p>}{f.client?.city && <p>{f.client.city}</p>}</div>
          {f.matter && <div><p className="text-xs text-neutral-500">{t("cab.matter")}</p><p className="font-medium">{f.matter.title}</p>
            <p className="font-mono text-xs" dir="ltr">{f.matter.reference}{f.matter.case_number ? ` · ${f.matter.case_number}` : ""}</p></div>}
        </section>
        <table className="mt-8 w-full text-sm">
          <thead><tr className="border-b text-xs text-neutral-500"><th className="py-2 text-start">{t("bill.description")}</th><th className="py-2 text-end">{t("bill.amountHt")}</th></tr></thead>
          <tbody>{f.lines.map((l, i) => (
            <tr key={i} className="border-b"><td className="py-2">{l.label}</td><td className="py-2 text-end tabular-nums">{money(l.amount, lang)}</td></tr>
          ))}</tbody>
        </table>
        <dl className="ms-auto mt-4 w-64 space-y-1 text-sm">
          <div className="flex justify-between"><dt>{t("bill.amountHt")}</dt><dd className="tabular-nums">{money(f.amount_ht, lang)}</dd></div>
          <div className="flex justify-between"><dt>{t("bill.vat")} ({f.vat_rate / 100} %)</dt><dd className="tabular-nums">{money(f.vat, lang)}</dd></div>
          <div className="flex justify-between border-t pt-1 font-semibold"><dt>{t("bill.total")}</dt><dd className="tabular-nums">{money(f.amount_ttc, lang)}</dd></div>
          {f.paid > 0 && <div className="flex justify-between"><dt>{t("bill.paid")}</dt><dd className="tabular-nums">{money(f.paid, lang)}</dd></div>}
          <div className="flex justify-between font-semibold"><dt>{t("bill.balance")}</dt><dd className="tabular-nums">{money(f.balance, lang)}</dd></div>
        </dl>
        <p className="mt-6 text-sm">{t("adm.colStatus")} : {status(f.status)}</p>
      </article>
    </div>
  );
}
