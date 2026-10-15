import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Card, Select } from "@/components/biz";
import { AgendaList, CabinetNav } from "@/components/cabinet";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { firmAgenda } from "@/lib/api-practice";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/cabinet/agenda")({
  head: () => ({ meta: [{ title: "الأجندة · Agenda" }] }),
  component: AgendaPage,
});

const iso = (d: Date) => d.toISOString().slice(0, 10);

function AgendaPage() {
  const { t, lang } = useI18n();
  const [start, setStart] = useState(() => iso(new Date()));
  const [days, setDays] = useState("14");
  const [mine, setMine] = useState(false);
  const a = useQuery({ queryKey: ["firm-agenda", start, days, mine], queryFn: () => firmAgenda(start, Number(days), mine) });
  const move = (n: number) => { const d = new Date(`${start}T12:00:00`); d.setDate(d.getDate() + n * Number(days)); setStart(iso(d)); };
  return (
    <AppShell title={t("cab.agenda")} description={t("cab.agendaSubtitle")}>
      <CabinetNav />
      <Card action={
        <div className="flex flex-wrap items-center gap-2">
          <Button size="icon" variant="ghost" onClick={() => move(-1)} aria-label={t("listing.prev")}>{lang === "ar" ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}</Button>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="h-9 rounded-md border bg-background px-2 text-sm" aria-label={t("crm.from")} />
          <Button size="icon" variant="ghost" onClick={() => move(1)} aria-label={t("listing.next")}>{lang === "ar" ? <ChevronLeft className="size-4" /> : <ChevronRight className="size-4" />}</Button>
          <Select value={days} onChange={setDays} label={t("cab.period")} className="h-9"
                  options={[{ value: "7", label: t("cab.week") }, { value: "14", label: t("cab.twoWeeks") }, { value: "31", label: t("cab.month") }]} />
          <label className="flex items-center gap-2 text-sm"><Switch checked={mine} onCheckedChange={setMine} />{t("cab.mineOnly")}</label>
          <Button size="sm" variant="outline" onClick={() => setStart(iso(new Date()))}>{t("cab.today")}</Button>
        </div>
      }>
        <AgendaList agenda={a.data} empty={t("cab.nothingSoon")} />
      </Card>
    </AppShell>
  );
}
