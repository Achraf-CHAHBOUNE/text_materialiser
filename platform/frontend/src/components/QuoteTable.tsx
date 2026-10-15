import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";

import { Badge, day, Empty, money, STATUS_TONE, Table, Td } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { acceptQuote, refuseQuote, sendQuote, type Quote } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

/** Quotes with what can be done to each: send, accept, refuse. Used here and on an organization. */
export function QuoteTable({ rows, showOrg }: { rows: Quote[]; showOrg?: boolean }) {
  const { t, lang, status } = useI18n();
  const qc = useQueryClient();
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["quotes"] }); void qc.invalidateQueries({ queryKey: ["org"] }); };
  const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : t("adm.failed"));
  const send = useMutation({ mutationFn: sendQuote, onSuccess: () => { toast.success(t("quote.sent")); refresh(); }, onError: fail });
  const accept = useMutation({ mutationFn: acceptQuote, onSuccess: (r) => { toast.success(`${t("quote.accepted")} — ${r.invoice.number}`); refresh(); }, onError: fail });
  const refuse = useMutation({ mutationFn: refuseQuote, onSuccess: refresh, onError: fail });
  if (rows.length === 0) return <Empty>{t("quote.none")}</Empty>;
  return (
    <Table head={[t("bill.number"), ...(showOrg ? [t("crm.org")] : []), t("bill.issued"), t("quote.validUntil"), t("bill.amountHt"), t("adm.colStatus"), ""]} minWidth="52rem">
      {rows.map((q) => (
        <tr key={q.id}>
          <Td><Link to="/quote/$quoteId" params={{ quoteId: String(q.id) }} className="font-mono text-teal hover:underline" dir="ltr">{q.number}</Link>
            <p className="text-xs text-muted-foreground">{q.lines.map((l) => l.label).join(" · ")}</p></Td>
          {showOrg && <Td><Link to="/crm/orgs/$orgId" params={{ orgId: String(q.org_id) }} className="hover:text-teal">{q.org_name}</Link></Td>}
          <Td>{day(q.issued_on)}</Td><Td>{day(q.valid_until)}</Td>
          <Td className="tabular-nums">{money(q.amount_ht, lang)}</Td>
          <Td><Badge tone={STATUS_TONE[q.status]}>{status(q.status)}</Badge></Td>
          <Td>
            {(q.status === "draft" || q.status === "sent") && (
              <div className="flex flex-wrap gap-1">
                <Button size="sm" variant="outline" onClick={() => send.mutate(q.id)}>{q.status === "draft" ? t("quote.send") : t("quote.resend")}</Button>
                <Button size="sm" onClick={() => { if (window.confirm(t("quote.acceptConfirm"))) accept.mutate(q.id); }}>{t("quote.accept")}</Button>
                <Button size="sm" variant="ghost" onClick={() => refuse.mutate(q.id)}>{t("quote.refuse")}</Button>
              </div>
            )}
            {q.invoice_id && <Link to="/invoice/$invoiceId" params={{ invoiceId: String(q.invoice_id) }} className="text-xs text-teal underline">{t("bill.invoice")}</Link>}
          </Td>
        </tr>
      ))}
    </Table>
  );
}
