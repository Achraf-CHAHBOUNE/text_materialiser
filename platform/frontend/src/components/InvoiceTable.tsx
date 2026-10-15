import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, day, Empty, money, Select, STATUS_TONE, Table, Td } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { addPayment, cancelInvoice, type Invoice } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

const fail = (fallback: string) => (e: unknown) => toast.error(e instanceof Error ? e.message : fallback);

/** Invoices with what is left to pay, a payment recorded in place, a cancel for the unpaid. */
export function InvoiceTable({ rows, onChange, lang, showOrg }: { rows: Invoice[]; onChange: () => void; lang: "ar" | "fr"; showOrg?: boolean }) {
  const { t, status } = useI18n();
  const [paying, setPaying] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("transfer");
  const [ref, setRef] = useState("");
  const pay = useMutation({
    mutationFn: (id: number) => addPayment(id, { amount: Math.round(parseFloat(amount.replace(",", ".")) * 100), method, reference: ref }),
    onSuccess: () => { toast.success(t("bill.paymentSaved")); setPaying(null); setAmount(""); setRef(""); onChange(); }, onError: fail(t("adm.failed")),
  });
  const cancel = useMutation({ mutationFn: cancelInvoice, onSuccess: onChange, onError: fail(t("adm.failed")) });
  if (rows.length === 0) return <Empty>{t("bill.none")}</Empty>;
  return (
    <Table head={[t("bill.number"), ...(showOrg ? [t("crm.org")] : []), t("bill.issued"), t("bill.due"), t("bill.total"), t("bill.balance"), t("adm.colStatus"), ""]} minWidth="52rem">
      {rows.map((i) => (
        <tr key={i.id}>
          <Td><Link to="/invoice/$invoiceId" params={{ invoiceId: String(i.id) }} className="font-mono text-teal hover:underline" dir="ltr">{i.number}</Link>
            {i.description && <p className="text-xs text-muted-foreground">{i.description}</p>}</Td>
          {showOrg && <Td><Link to="/crm/orgs/$orgId" params={{ orgId: String(i.org_id) }} className="hover:text-teal">{i.org_name}</Link></Td>}
          <Td>{day(i.issued_on)}</Td><Td>{day(i.due_on)}</Td>
          <Td className="tabular-nums">{money(i.amount_ttc, lang)}</Td>
          <Td className="tabular-nums">{money(i.balance, lang)}</Td>
          <Td><Badge tone={STATUS_TONE[i.status]}>{status(i.status)}</Badge></Td>
          <Td>
            {(i.status === "sent" || i.status === "overdue") && paying !== i.id && (
              <div className="flex gap-1">
                <Button size="sm" variant="outline" onClick={() => { setPaying(i.id); setAmount(String(i.balance / 100)); }}>{t("bill.recordPayment")}</Button>
                {i.paid === 0 && <Button size="sm" variant="ghost" onClick={() => { if (window.confirm(t("bill.cancelConfirm"))) cancel.mutate(i.id); }}>{t("team.cancel")}</Button>}
              </div>
            )}
            {paying === i.id && (
              <form className="flex flex-wrap gap-1" onSubmit={(e) => { e.preventDefault(); pay.mutate(i.id); }}>
                <Input value={amount} onChange={(e) => setAmount(e.target.value)} className="h-8 w-24" dir="ltr" inputMode="decimal" aria-label={t("bill.amount")} />
                <Select value={method} onChange={setMethod} className="h-8 text-xs" label={t("bill.method")}
                        options={["transfer", "cheque", "cash", "card"].map((m) => ({ value: m, label: t(`pay.${m}` as "pay.cash") }))} />
                <Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder={t("bill.reference")} className="h-8 w-28" aria-label={t("bill.reference")} />
                <Button size="sm" type="submit" disabled={pay.isPending}>{t("adm.save")}</Button>
                <Button size="sm" type="button" variant="ghost" onClick={() => setPaying(null)}>×</Button>
              </form>
            )}
          </Td>
        </tr>
      ))}
    </Table>
  );
}

