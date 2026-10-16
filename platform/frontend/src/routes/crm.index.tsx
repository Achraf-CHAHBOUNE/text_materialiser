import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";

import { AppShell } from "@/components/AppShell";
import { Bars } from "@/components/Bars";
import { Card, day, Empty, money, Stat } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { leads, overview, updateLead } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/")({
  head: () => ({ meta: [{ title: "CRM" }] }),
  component: Dashboard,
});

/** The admin's first screen: the readers, the money, the contracts, what needs a look,
 *  and the requests that came in through the public page. */
function Dashboard() {
  const { t, lang, num } = useI18n();
  const qc = useQueryClient();
  const o = useQuery({ queryKey: ["overview"], queryFn: overview });
  const inbox = useQuery({ queryKey: ["leads", "new"], queryFn: () => leads("new") });
  const done = useMutation({ mutationFn: (x: { id: number; status: "contacted" | "rejected" }) => updateLead(x.id, x.status),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["leads"] }); void qc.invalidateQueries({ queryKey: ["overview"] }); } });
  const v = o.data;
  return (
    <AppShell title={t("crm.title")} description={t("crm.subtitleAdmin")}>
      <CrmNav />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("dash.readers")} value={v ? num(v.readers) : "—"}
              hint={v ? `${num(v.active_today)} ${t("dash.today")} · ${num(v.active_7d)} ${t("dash.week")} · ${num(v.active_30d)} ${t("dash.month")}` : undefined} />
        <Stat label={t("dash.receivedMonth")} value={v ? money(v.received_month, lang) : "—"} tone="good"
              hint={v ? `${t("dash.year")} ${money(v.received_year, lang)}` : undefined} />
        <Stat label={t("dash.owed")} value={v ? money(v.owed, lang) : "—"} tone={v?.owed ? "bad" : "default"}
              hint={v?.awaiting_payment ? <Link to="/crm/contracts" className="text-amber-700 underline dark:text-amber-300">{num(v.awaiting_payment)} {t("dash.awaiting")}</Link> : undefined} />
        <Stat label={t("dash.clientsOpen")} value={v ? num(v.clients_open) : "—"} tone={v?.contracts_ending ? "warn" : "default"}
              hint={v ? (v.contracts_ending ? `${num(v.contracts_ending)} ${t("dash.ending")}` : `${num(v.contracts_active)} ${t("dash.contractsRunning")}`) : undefined} />
      </div>
      {v && v.alerts > 0 && (
        <Link to="/crm/alerts" className={`mt-4 block rounded-xl border px-4 py-3 text-sm ${v.alerts_high ? "border-destructive/40 bg-destructive/10 text-destructive" : "bg-card"}`}>
          {num(v.alerts)} {t("dash.alerts")}{v.alerts_high ? ` · ${num(v.alerts_high)} ${t("dash.serious")}` : ""} →
        </Link>
      )}
      <Card title={t("trk.activity")} className="mt-4"><Bars rows={v?.usage.series ?? []} days={30} /></Card>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title={t("trk.topRead")}>
          {!v || v.usage.top_read.length === 0 ? <Empty>{t("hist.empty")}</Empty> : (
            <ul className="divide-y text-sm">{v.usage.top_read.slice(0, 8).map((r) => (
              <li key={r.doc_id} className="flex justify-between gap-2 py-1.5">
                <Link to="/ruling/$docId" params={{ docId: r.doc_id }} className="hover:text-teal">{t("ruling.decisionOf")} {num(r.decision_no ?? "")}</Link>
                <span className="tabular-nums text-muted-foreground">{num(r.count)} · {num(r.readers)} {t("trk.readersShort")}</span>
              </li>))}</ul>
          )}
        </Card>
        <Card title={`${t("dash.requests")}${inbox.data?.length ? ` (${num(inbox.data.length)})` : ""}`}>
          <p className="mb-2 text-xs text-muted-foreground">{t("dash.requestsHint")}</p>
          {inbox.data && inbox.data.length === 0 ? <Empty>{t("dash.noRequests")}</Empty> : (
            <ul className="divide-y text-sm">
              {(inbox.data ?? []).map((l) => (
                <li key={l.id} className="py-2">
                  <p className="font-medium">{l.full_name}{l.company && <span className="text-muted-foreground"> · {l.company}</span>}</p>
                  <p className="text-xs text-muted-foreground"><span dir="ltr">{l.email}</span>{l.phone && <> · <span dir="ltr">{l.phone}</span></>} · {day(l.created_at)}</p>
                  {l.message && <p className="mt-1 text-xs">{l.message}</p>}
                  <div className="mt-1 flex flex-wrap gap-1">
                    <Button asChild size="sm" className="h-7 text-xs">
                      <Link to="/crm/new" search={{ name: l.company || l.full_name, email: l.email, phone: l.phone, city: l.city, lead: l.id }}>
                        {t("dash.makeClient")}</Link>
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => done.mutate({ id: l.id, status: "contacted" })}>{t("dash.contacted")}</Button>
                    <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => done.mutate({ id: l.id, status: "rejected" })}>{t("dash.ignore")}</Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
