// Pieces the firm module's pages share: its tabs, and the agenda as a list of days.
import { Link, useRouterState } from "@tanstack/react-router";
import { AlarmClock, CalendarDays, CheckSquare, ShieldAlert } from "lucide-react";

import { Badge, day } from "@/components/biz";
import type { Agenda } from "@/lib/api-practice";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function CabinetNav() {
  const { t } = useI18n();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const tabs = [
    { to: "/cabinet", label: t("cab.home"), exact: true },
    { to: "/cabinet/agenda", label: t("cab.agenda") },
    { to: "/cabinet/matters", label: t("cab.matters") },
    { to: "/cabinet/clients", label: t("cab.clients") },
    { to: "/cabinet/fees", label: t("cab.fees") },
  ];
  return (
    <nav className="mb-5 flex flex-wrap gap-1 rounded-xl border bg-card p-1 text-sm" aria-label={t("nav.cabinet")}>
      {tabs.map((x) => {
        const on = x.exact ? path === x.to || path === `${x.to}/` : path.startsWith(x.to);
        return (
          <Link key={x.to} to={x.to} className={cn("rounded-lg px-3 py-1.5 transition-colors",
            on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground")}>
            {x.label}
          </Link>
        );
      })}
    </nav>
  );
}

const WEEKDAYS = {
  fr: ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."],
  ar: ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"],
};

/** Hearings, deadlines and tasks, grouped by day; what is late comes first, in red. */
export function AgendaList({ agenda, empty }: { agenda: Agenda | undefined; empty: string }) {
  const { t, lang } = useI18n();
  if (!agenda) return null;
  const today = new Date().toISOString().slice(0, 10);
  type Item = { date: string; kind: "hearing" | "deadline" | "task"; text: string; matterId: number | null; ref: string; late: boolean; unverified?: boolean };
  const items: Item[] = [
    ...agenda.hearings.map((h) => ({ date: h.date, kind: "hearing" as const, matterId: h.matter_id, ref: h.matter_reference ?? "", late: false,
      text: `${h.time ? `${h.time} · ` : ""}${h.matter_title ?? ""}${h.court ? ` — ${h.court}` : ""}${h.room ? ` (${h.room})` : ""}${h.purpose ? ` · ${h.purpose}` : ""}` })),
    ...agenda.deadlines.map((d) => ({ date: d.due_on, kind: "deadline" as const, matterId: d.matter_id, ref: d.matter_reference ?? "",
      late: d.due_on < today, unverified: !d.verified_by,
      text: `${t(`dl.${d.kind}` as "dl.appeal")} — ${d.matter_title ?? ""}` })),
    ...agenda.tasks.map((x) => ({ date: x.due_on, kind: "task" as const, matterId: x.matter_id, ref: x.matter_reference ?? "",
      late: x.due_on < today, text: x.title })),
  ].sort((a, b) => a.date.localeCompare(b.date) || a.kind.localeCompare(b.kind));
  if (items.length === 0) return <p className="py-6 text-center text-sm text-muted-foreground">{empty}</p>;
  const days = [...new Set(items.map((i) => (i.date < today ? "late" : i.date)))];
  const Icon = { hearing: CalendarDays, deadline: AlarmClock, task: CheckSquare };
  return (
    <div className="space-y-4">
      {days.map((d) => (
        <section key={d}>
          <h3 className={cn("mb-1.5 text-xs font-semibold", d === "late" ? "text-destructive" : d === today ? "text-teal" : "text-muted-foreground")}>
            {d === "late" ? t("cab.late") : `${WEEKDAYS[lang][new Date(`${d}T12:00:00`).getDay()]} ${day(d)}${d === today ? ` · ${t("cab.today")}` : ""}`}
          </h3>
          <ul className="divide-y rounded-xl border bg-card">
            {items.filter((i) => (d === "late" ? i.date < today : i.date === d)).map((i, k) => {
              const I = Icon[i.kind];
              const body = (
                <span className="flex items-start gap-2">
                  <I className={cn("mt-0.5 size-4 shrink-0", i.kind === "deadline" ? "text-amber-600" : i.kind === "hearing" ? "text-teal" : "text-muted-foreground")} aria-hidden />
                  <span className="min-w-0 flex-1">
                    {i.ref && <span className="me-1 font-mono text-xs text-muted-foreground" dir="ltr">{i.ref}</span>}
                    {i.text}
                    {i.late && <span className="ms-1 text-xs text-destructive">({day(i.date)})</span>}
                  </span>
                  {i.unverified && <Badge tone="warn"><ShieldAlert className="me-1 size-3" />{t("cab.toVerify")}</Badge>}
                </span>
              );
              return (
                <li key={k} className="px-3 py-2 text-sm">
                  {i.matterId ? <Link to="/cabinet/matters/$matterId" params={{ matterId: String(i.matterId) }} className="block hover:text-teal">{body}</Link> : body}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
