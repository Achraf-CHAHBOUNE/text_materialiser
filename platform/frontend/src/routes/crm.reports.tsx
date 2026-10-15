import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Download } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Card, money, Stat, Table, Td } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { exportCsv, reports } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/reports")({
  head: () => ({ meta: [{ title: "Rapports · CRM" }] }),
  component: ReportsPage,
});

const MONTHS = {
  fr: ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
  ar: ["يناير", "فبراير", "مارس", "أبريل", "ماي", "يونيو", "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر"],
};

function ReportsPage() {
  const { t, lang, num, status } = useI18n();
  const r = useQuery({ queryKey: ["reports"], queryFn: reports });
  const d = r.data;
  const label = (m: string) => `${MONTHS[lang][Number(m.slice(5)) - 1]} ${m.slice(2, 4)}`;
  const top = Math.max(1, ...(d?.revenue ?? []).map((x) => x.amount));
  const dl = (what: "leads" | "orgs" | "invoices" | "payments") =>
    exportCsv(what).catch((e) => toast.error(e instanceof Error ? e.message : t("adm.failed")));
  return (
    <AppShell title={t("rep.title")} description={t("rep.subtitle")}>
      <CrmNav />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("rep.mrr")} value={d ? money(d.mrr, lang) : "—"} tone="good" hint={t("pub.exclVat")} />
        <Stat label={t("rep.arr")} value={d ? money(d.arr, lang) : "—"} />
        <Stat label={t("rep.paying")} value={d ? num(d.paying_customers) : "—"} hint={d ? `${t("rep.arpa")} ${money(d.arpa, lang)}` : undefined} />
        <Stat label={t("rep.forecast")} value={d ? money(d.forecast, lang) : "—"} hint={d ? `${t("rep.pipeline")} ${money(d.pipeline_open, lang)}` : undefined} />
        <Stat label={t("rep.conversion")} value={d ? `${num(d.conversion_rate)} %` : "—"} hint={d ? `${num(d.converted_12m)} / ${num(d.leads_12m)} ${t("rep.leads12")}` : undefined} />
        <Stat label={t("rep.winRate")} value={d ? `${num(d.win_rate)} %` : "—"} />
      </div>

      <Card title={t("rep.revenue")} className="mt-4">
        <div className="flex h-48 items-end gap-2" role="img" aria-label={t("rep.revenue")}>
          {(d?.revenue ?? []).map((x) => (
            <div key={x.month} className="flex flex-1 flex-col items-center gap-1">
              <span className="text-[10px] tabular-nums text-muted-foreground">{x.amount ? Math.round(x.amount / 100).toLocaleString("fr-MA") : ""}</span>
              <div className="w-full rounded-t bg-teal/70" style={{ height: `${Math.max(2, (x.amount / top) * 150)}px` }} title={money(x.amount, lang)} />
              <span className="text-[10px] text-muted-foreground">{label(x.month)}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title={t("rep.movements")}>
          <Table head={[t("rep.month"), t("rep.new"), t("rep.churned")]} minWidth="20rem">
            {(d?.new_customers ?? []).map((x, i) => (
              <tr key={x.month}>
                <Td>{label(x.month)}</Td>
                <Td className="tabular-nums text-teal">{x.count ? `+${num(x.count)}` : "—"}</Td>
                <Td className="tabular-nums text-destructive">{d?.churned[i]?.count ? `−${num(d.churned[i]!.count)}` : "—"}</Td>
              </tr>
            ))}
          </Table>
        </Card>
        <div className="space-y-4">
          <Card title={t("rep.byPlan")}>
            <ul className="space-y-1 text-sm">
              {Object.entries(d?.plans ?? {}).map(([plan, n]) => (
                <li key={plan} className="flex justify-between"><span>{plan}</span><span className="tabular-nums">{num(n)}</span></li>
              ))}
            </ul>
          </Card>
          <Card title={t("rep.odds")}>
            <ul className="space-y-1 text-sm">
              {Object.entries(d?.stage_odds ?? {}).map(([stage, p]) => (
                <li key={stage} className="flex justify-between"><span>{status(stage)}</span><span className="tabular-nums">{num(Math.round(p * 100))} %</span></li>
              ))}
            </ul>
          </Card>
          <Card title={t("rep.exports")}>
            <div className="flex flex-wrap gap-2">
              {(["leads", "orgs", "invoices", "payments"] as const).map((w) => (
                <Button key={w} size="sm" variant="outline" onClick={() => void dl(w)}>
                  <Download className="size-4" />{t(`rep.export.${w}` as "rep.export.leads")}
                </Button>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
