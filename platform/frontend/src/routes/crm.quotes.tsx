import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Card, money, Select, Stat } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { QuoteTable } from "@/components/QuoteTable";
import { quotes } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/quotes")({
  head: () => ({ meta: [{ title: "Devis · CRM" }] }),
  component: Quotes,
});

function Quotes() {
  const { t, lang, num, status } = useI18n();
  const [filter, setFilter] = useState("");
  const list = useQuery({ queryKey: ["quotes", filter], queryFn: () => quotes({ status: filter }) });
  const rows = list.data ?? [];
  const open = rows.filter((q) => q.status === "draft" || q.status === "sent");
  return (
    <AppShell title={t("quote.title")} description={t("quote.subtitle")}>
      <CrmNav />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat label={t("quote.open")} value={num(open.length)} />
        <Stat label={t("quote.openValue")} value={money(open.reduce((a, q) => a + q.amount_ht, 0), lang)} hint={t("pub.exclVat")} />
        <Stat label={t("quote.acceptedRate")} tone="good"
              value={`${num(Math.round(100 * rows.filter((q) => q.status === "accepted").length /
                Math.max(1, rows.filter((q) => ["accepted", "refused", "expired"].includes(q.status)).length)))} %`} />
      </div>
      <Card action={<Select value={filter} onChange={setFilter} label={t("adm.colStatus")}
                            options={[{ value: "", label: t("sup.all") }, ...["draft", "sent", "accepted", "refused", "expired"].map((s) => ({ value: s, label: status(s) }))]} />}>
        <p className="mb-3 text-xs text-muted-foreground">{t("quote.howTo")}</p>
        <QuoteTable rows={rows} showOrg />
      </Card>
    </AppShell>
  );
}
