import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, Select, Stat, STATUS_TONE, Table, Td } from "@/components/biz";
import { CabinetNav } from "@/components/cabinet";
import { feeNotes } from "@/lib/api-practice";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/cabinet/fees")({
  head: () => ({ meta: [{ title: "الأتعاب · Honoraires" }] }),
  component: Fees,
});

function Fees() {
  const { t, lang, num, status } = useI18n();
  const [filter, setFilter] = useState("");
  const list = useQuery({ queryKey: ["fee-notes", filter], queryFn: () => feeNotes(filter) });
  const rows = list.data ?? [];
  const open = rows.filter((f) => f.status === "sent" || f.status === "overdue");
  return (
    <AppShell title={t("cab.fees")} description={t("cab.feesSubtitle")}>
      <CabinetNav />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat label={t("bill.toCollect")} value={money(open.reduce((a, f) => a + f.balance, 0), lang)} />
        <Stat label={status("overdue")} value={num(rows.filter((f) => f.status === "overdue").length)} tone="bad" />
        <Stat label={t("bill.collected")} value={money(rows.reduce((a, f) => a + f.paid, 0), lang)} tone="good" />
      </div>
      <Card action={<Select value={filter} onChange={setFilter} label={t("adm.colStatus")}
                            options={[{ value: "", label: t("sup.all") }, ...["sent", "overdue", "paid", "cancelled"].map((s) => ({ value: s, label: status(s) }))]} />}>
        {rows.length === 0 ? <Empty>{t("cab.noFees")}</Empty> : (
          <Table head={[t("bill.number"), t("cab.client"), t("bill.issued"), t("bill.due"), t("bill.total"), t("bill.balance"), t("adm.colStatus")]} minWidth="52rem">
            {rows.map((f) => (
              <tr key={f.id}>
                <Td><Link to="/fee/$feeId" params={{ feeId: String(f.id) }} className="font-mono text-teal hover:underline" dir="ltr">{f.number}</Link></Td>
                <Td>{f.client_name || "—"}</Td><Td>{day(f.issued_on)}</Td><Td>{day(f.due_on)}</Td>
                <Td className="tabular-nums">{money(f.amount_ttc, lang)}</Td><Td className="tabular-nums">{money(f.balance, lang)}</Td>
                <Td><Badge tone={STATUS_TONE[f.status]}>{status(f.status)}</Badge></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </AppShell>
  );
}
