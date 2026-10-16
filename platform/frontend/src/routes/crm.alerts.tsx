import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, CalendarClock, Download, Gauge, Laptop, Moon, Network, Wallet } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { crmAlerts, type AlertItem } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/alerts")({
  head: () => ({ meta: [{ title: "Alertes · CRM" }] }),
  component: Alerts,
});

const ICON = { shared_ips: Network, many_devices: Laptop, quota_hit: Download, too_fast: Gauge, inactive: Moon,
  awaiting_payment: Wallet, ending: CalendarClock, balance: Wallet };
const TONE = { high: "bad", medium: "warn", low: "muted" } as const;

/** What deserves a look, the serious first: accounts used like shared ones, download
 *  limits hit, reading at a pace no person reads, paying readers gone quiet, and the
 *  contracts that wait for money or are about to end. */
function Alerts() {
  const { t, lang, num } = useI18n();
  const q = useQuery({ queryKey: ["crm-alerts"], queryFn: crmAlerts });
  const line = (a: AlertItem) => {
    switch (a.kind) {
      case "shared_ips": return `${t("al.sharedIps")} (${num(a.count)}) — ${a.detail}`;
      case "many_devices": return `${t("al.manyDevices")} (${num(a.count)})`;
      case "quota_hit": return `${t("al.quotaHit")} ${num(a.count)} ${t("al.days")}`;
      case "too_fast": return `${t("al.tooFast")} (${num(a.count)})`;
      case "inactive": return a.at ? `${t("al.inactive")} ${num(a.count)} ${t("al.days")}` : t("al.neverRead");
      case "awaiting_payment": return `${t("al.awaiting")} ${a.detail} — ${money(a.count, lang)}`;
      case "ending": return `${t("al.ending")} ${num(a.count)} ${t("al.days")} (${a.detail})`;
      case "balance": return `${t("al.balance")} ${money(a.count, lang)}`;
    }
  };
  return (
    <AppShell title={t("crm.alerts")} description={t("al.subtitle")}>
      <CrmNav />
      <Card>
        {q.data && q.data.length === 0 ? <Empty>{t("al.none")}</Empty> : (
          <ul className="divide-y">
            {(q.data ?? []).map((a, i) => {
              const I = ICON[a.kind] ?? AlertTriangle;
              return (
                <li key={i} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                  <I className={`size-4 shrink-0 ${a.level === "high" ? "text-destructive" : a.level === "medium" ? "text-amber-600" : "text-muted-foreground"}`} aria-hidden />
                  <Badge tone={TONE[a.level]}>{t(`al.level.${a.level}` as "al.level.high")}</Badge>
                  {a.email ? (
                    <Link to="/crm/users/$email" params={{ email: a.email }} className="font-medium text-teal hover:underline" dir="ltr">{a.email}</Link>
                  ) : a.org_id ? (
                    <Link to="/crm/orgs/$orgId" params={{ orgId: String(a.org_id) }} className="font-medium text-teal hover:underline">{a.org}</Link>
                  ) : null}
                  <span>{line(a)}</span>
                  {a.at && <span className="ms-auto text-xs text-muted-foreground">{day(a.at)}</span>}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}
