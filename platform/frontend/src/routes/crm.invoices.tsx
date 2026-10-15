import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Card, money, Select, Stat } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { InvoiceTable } from "@/components/InvoiceTable";
import { allInvoices } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/invoices")({
  head: () => ({ meta: [{ title: "Factures · CRM" }] }),
  component: AllInvoices,
});

function AllInvoices() {
  const { t, lang, num, status } = useI18n();
  const qc = useQueryClient();
  const [filter, setFilter] = useState("");
  const list = useQuery({ queryKey: ["all-invoices", filter], queryFn: () => allInvoices(filter) });
  const rows = list.data ?? [];
  const open = rows.filter((i) => i.status === "sent" || i.status === "overdue");
  return (
    <AppShell title={t("bill.invoices")} description={t("bill.subtitle")}>
      <CrmNav />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat label={t("bill.toCollect")} value={money(open.reduce((a, i) => a + i.balance, 0), lang)} />
        <Stat label={status("overdue")} value={num(rows.filter((i) => i.status === "overdue").length)} tone="bad" />
        <Stat label={t("bill.collected")} value={money(rows.reduce((a, i) => a + i.paid, 0), lang)} tone="good" />
      </div>
      <Card action={<Select value={filter} onChange={setFilter} label={t("adm.colStatus")}
                            options={[{ value: "", label: t("sup.all") }, ...["sent", "overdue", "paid", "cancelled"].map((s) => ({ value: s, label: status(s) }))]} />}>
        <InvoiceTable rows={rows} lang={lang} showOrg onChange={() => void qc.invalidateQueries({ queryKey: ["all-invoices"] })} />
      </Card>
    </AppShell>
  );
}
