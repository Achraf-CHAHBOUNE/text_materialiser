import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Card, money, Stat } from "@/components/biz";
import { AgendaList, CabinetNav } from "@/components/cabinet";
import { Input } from "@/components/ui/input";
import { firmDashboard, firmSearch } from "@/lib/api-practice";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/cabinet/")({
  head: () => ({ meta: [{ title: "المكتب · Cabinet" }] }),
  component: CabinetHome,
});

function CabinetHome() {
  const { t, lang, num } = useI18n();
  const d = useQuery({ queryKey: ["firm-dashboard"], queryFn: firmDashboard });
  const [q, setQ] = useState("");
  const found = useQuery({ queryKey: ["firm-search", q], queryFn: () => firmSearch(q), enabled: q.trim().length >= 2 });
  const v = d.data;
  return (
    <AppShell title={t("cab.title")} description={t("cab.subtitle")}>
      <CabinetNav />
      <div className="relative mb-4">
        <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("cab.search")} aria-label={t("cab.search")} className="h-11 ps-9" />
        {found.data && q.trim().length >= 2 && (
          <div className="absolute inset-x-0 top-12 z-20 max-h-80 overflow-auto rounded-xl border bg-card p-2 shadow-lg">
            {found.data.matters.map((m) => (
              <Link key={`m${m.id}`} to="/cabinet/matters/$matterId" params={{ matterId: String(m.id) }} className="block rounded-md px-2 py-1.5 text-sm hover:bg-accent">
                <span className="me-2 font-mono text-xs text-muted-foreground" dir="ltr">{m.reference}</span>{m.title}
                {m.client_name && <span className="text-muted-foreground"> · {m.client_name}</span>}
              </Link>
            ))}
            {found.data.clients.map((c) => (
              <Link key={`c${c.id}`} to="/cabinet/clients/$clientId" params={{ clientId: String(c.id) }} className="block rounded-md px-2 py-1.5 text-sm hover:bg-accent">
                {c.full_name}<span className="text-muted-foreground"> · {t("cab.client")}</span>
              </Link>
            ))}
            {found.data.matters.length + found.data.clients.length === 0 && <p className="px-2 py-1.5 text-sm text-muted-foreground">{t("results.none")}</p>}
          </div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("cab.hearingsToday")} value={v ? num(v.hearings_today) : "—"} hint={v ? `${num(v.hearings_week)} ${t("cab.thisWeek")}` : undefined} tone={v?.hearings_today ? "warn" : "default"} />
        <Stat label={t("cab.deadlinesSoon")} value={v ? num(v.deadlines_soon) : "—"}
              hint={v ? `${num(v.deadlines_late)} ${t("cab.late")} · ${num(v.deadlines_unverified)} ${t("cab.toVerify")}` : undefined}
              tone={v?.deadlines_late ? "bad" : v?.deadlines_soon ? "warn" : "default"} />
        <Stat label={t("cab.openMatters")} value={v ? num(v.open_matters) : "—"} hint={v ? `${num(v.clients)} ${t("cab.clients")}` : undefined} />
        <Stat label={t("cab.unpaid")} value={v ? money(v.fees_unpaid, lang) : "—"}
              hint={v ? `${t("cab.collectedMonth")} ${money(v.collected_month, lang)}` : undefined} tone={v?.fees_overdue ? "bad" : "default"} />
      </div>
      <Card title={t("cab.next7")} className="mt-4" action={<Link to="/cabinet/agenda" className="text-sm text-teal hover:underline">{t("cab.fullAgenda")}</Link>}>
        <AgendaList agenda={v?.agenda} empty={t("cab.nothingSoon")} />
      </Card>
    </AppShell>
  );
}
