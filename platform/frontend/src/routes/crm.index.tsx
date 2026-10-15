import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, Select, Stat, STATUS_TONE } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { crmDashboard, pipeline, STAGES, updateOpp, type Stage } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/")({
  head: () => ({ meta: [{ title: "CRM" }] }),
  component: CrmHome,
});

function CrmHome() {
  const { t, lang, num, status } = useI18n();
  const qc = useQueryClient();
  const d = useQuery({ queryKey: ["crm-dashboard"], queryFn: crmDashboard });
  const opps = useQuery({ queryKey: ["pipeline"], queryFn: pipeline });
  const move = useMutation({
    mutationFn: (x: { id: number; stage: Stage }) => updateOpp(x.id, { stage: x.stage }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["pipeline"] }); void qc.invalidateQueries({ queryKey: ["crm-dashboard"] }); },
  });
  const v = d.data;
  return (
    <AppShell title={t("crm.title")} description={t("crm.subtitle")}>
      <CrmNav />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label={t("crm.newLeads")} value={v ? num(v.new_leads) : "—"} tone={v?.new_leads ? "warn" : "default"} />
        <Stat label={t("crm.customers")} value={v ? num(v.customers) : "—"} />
        <Stat label={t("crm.revenueMonth")} value={v ? money(v.revenue_month, lang) : "—"} tone="good" />
        <Stat label={t("crm.outstanding")} value={v ? money(v.outstanding, lang) : "—"}
              hint={v?.overdue_invoices ? `${num(v.overdue_invoices)} ${status("overdue")}` : undefined}
              tone={v?.overdue_invoices ? "bad" : "default"} />
        <Stat label={t("crm.myTasksDue")} value={v ? num(v.my_tasks_due) : "—"} tone={v?.my_tasks_due ? "warn" : "default"} />
      </div>

      <Card title={t("crm.pipeline")} className="mt-4">
        <div className="grid gap-3 overflow-x-auto md:grid-cols-3 xl:grid-cols-6">
          {STAGES.map((st) => {
            const col = (opps.data ?? []).filter((o) => o.stage === st);
            const sum = v?.pipeline.find((p) => p.stage === st);
            return (
              <div key={st} className="min-w-44 rounded-xl bg-muted/40 p-2">
                <div className="mb-2 flex items-center justify-between px-1 text-xs font-semibold">
                  <Badge tone={STATUS_TONE[st]}>{status(st)}</Badge>
                  <span className="text-muted-foreground">{num(sum?.count ?? 0)}</span>
                </div>
                <div className="space-y-2">
                  {col.slice(0, 12).map((o) => (
                    <div key={o.id} className="rounded-lg border bg-card p-2 text-xs shadow-xs">
                      <Link to="/crm/orgs/$orgId" params={{ orgId: String(o.org_id) }} className="font-medium hover:text-teal">{o.org_name}</Link>
                      {o.value > 0 && <p className="tabular-nums text-muted-foreground">{money(o.value, lang)}</p>}
                      <Select value={o.stage} onChange={(s) => move.mutate({ id: o.id, stage: s as Stage })}
                              className="mt-1 h-7 w-full text-xs" label={t("crm.stage")}
                              options={STAGES.map((s) => ({ value: s, label: status(s) }))} />
                    </div>
                  ))}
                  {col.length > 12 && <p className="px-1 text-xs text-muted-foreground">+{num(col.length - 12)}</p>}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title={t("crm.renewals")}>
          {v && v.renewals.length === 0 ? <Empty>{t("crm.noRenewals")}</Empty> : (
            <ul className="divide-y text-sm">
              {(v?.renewals ?? []).map((r) => (
                <li key={`${r.org_id}-${r.ends_on}`} className="flex items-center justify-between gap-2 py-2">
                  <Link to="/crm/orgs/$orgId" params={{ orgId: String(r.org_id) }} className="hover:text-teal">{r.name}</Link>
                  <span className="flex items-center gap-2 text-xs">
                    <Badge tone={STATUS_TONE[r.status]}>{status(r.status)}</Badge>
                    {day(r.ends_on)} · {num(r.days_left)} {t("crm.days")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title={t("crm.atRisk")}>
          <p className="mb-2 text-xs text-muted-foreground">{t("crm.atRiskHint")}</p>
          {v && v.at_risk.length === 0 ? <Empty>{t("crm.noRisk")}</Empty> : (
            <ul className="divide-y text-sm">
              {(v?.at_risk ?? []).map((r) => (
                <li key={r.id} className="py-2">
                  <Link to="/crm/orgs/$orgId" params={{ orgId: String(r.id) }} className="hover:text-teal">{r.name}</Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
