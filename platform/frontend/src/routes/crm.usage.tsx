import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Bars } from "@/components/Bars";
import { Card, day, Empty, Select, Stat, Table, Td } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { exportActivity, usage } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/usage")({
  head: () => ({ meta: [{ title: "Usage · CRM" }] }),
  component: UsagePage,
});

function UsagePage() {
  const { t, num, chamber } = useI18n();
  const [days, setDays] = useState("30");
  const q = useQuery({ queryKey: ["usage", days], queryFn: () => usage(Number(days)) });
  const d = q.data;
  const rulingRow = (r: {
    doc_id: string;
    count: number;
    readers: number;
    decision_no?: string;
    chamber?: string;
    date?: string;
  }) => (
    <tr key={r.doc_id}>
      <Td>
        <Link to="/ruling/$docId" params={{ docId: r.doc_id }} className="hover:text-teal">
          {t("ruling.decisionOf")} {num(r.decision_no ?? "")}
        </Link>
        <p className="text-xs text-muted-foreground">
          {chamber(r.chamber ?? "")} · {r.date}
        </p>
      </Td>
      <Td className="tabular-nums">{num(r.count)}</Td>
      <Td className="tabular-nums">{num(r.readers)}</Td>
    </tr>
  );
  return (
    <AppShell
      title={t("trk.usage")}
      description={t("trk.usageSubtitle")}
      action={
        <div className="flex gap-2">
          <Select
            value={days}
            onChange={setDays}
            label={t("cab.period")}
            className="h-9"
            options={[
              { value: "7", label: `7 ${t("crm.days")}` },
              { value: "30", label: `30 ${t("crm.days")}` },
              { value: "90", label: `90 ${t("crm.days")}` },
              { value: "365", label: `365 ${t("crm.days")}` },
            ]}
          />
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              void exportActivity(Number(days)).catch(() => toast.error(t("adm.failed")))
            }
          >
            <Download className="size-4" />
            {t("trk.export")}
          </Button>
        </div>
      }
    >
      <CrmNav />
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat
              label={t("trk.activeReaders")}
              value={`${num(d.active_readers)} / ${num(d.readers)}`}
              tone="good"
            />
            <Stat label={t("trk.reads")} value={num(d.totals.view ?? 0)} />
            <Stat label={t("trk.downloads")} value={num(d.totals.download ?? 0)} />
            <Stat
              label={t("trk.searches")}
              value={num((d.totals.search ?? 0) + (d.totals.search_empty ?? 0))}
              hint={`${num(d.totals.search_empty ?? 0)} ${t("trk.empty")}`}
            />
            <Stat label={t("trk.logins")} value={num(d.totals.login ?? 0)} />
          </div>
          <Card className="mt-4" title={t("trk.activity")}>
            <Bars rows={d.series} days={Number(days)} />
          </Card>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title={t("trk.topRead")}>
              {d.top_read.length === 0 ? (
                <Empty>{t("hist.empty")}</Empty>
              ) : (
                <Table
                  head={[t("ruling.decisionOf"), t("trk.times"), t("trk.readersShort")]}
                  minWidth="22rem"
                >
                  {d.top_read.map(rulingRow)}
                </Table>
              )}
            </Card>
            <Card title={t("trk.topDownloaded")}>
              {d.top_downloaded.length === 0 ? (
                <Empty>{t("hist.empty")}</Empty>
              ) : (
                <Table
                  head={[t("ruling.decisionOf"), t("trk.times"), t("trk.readersShort")]}
                  minWidth="22rem"
                >
                  {d.top_downloaded.map(rulingRow)}
                </Table>
              )}
            </Card>
            <Card title={t("trk.topSearches")}>
              {d.top_searches.length === 0 ? (
                <Empty>{t("hist.empty")}</Empty>
              ) : (
                <ul className="divide-y text-sm">
                  {d.top_searches.map((s) => (
                    <li key={s.query} className="flex justify-between gap-2 py-1.5">
                      <span>« {s.query} »</span>
                      <span className="tabular-nums">{num(s.count)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title={t("trk.emptySearches")}>
              <p className="mb-2 text-xs text-muted-foreground">{t("trk.emptyHint")}</p>
              {d.empty_searches.length === 0 ? (
                <Empty>{t("trk.noEmpty")}</Empty>
              ) : (
                <ul className="divide-y text-sm">
                  {d.empty_searches.map((s) => (
                    <li key={s.query} className="flex justify-between gap-2 py-1.5">
                      <span>« {s.query} »</span>
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {num(s.count)} · {day(s.last)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title={t("trk.topUsers")} className="lg:col-span-2">
              {d.top_users.length === 0 ? (
                <Empty>{t("hist.empty")}</Empty>
              ) : (
                <Table
                  head={[t("trk.reader"), t("trk.reads"), t("trk.downloads"), t("trk.searches")]}
                >
                  {d.top_users.map((u) => (
                    <tr key={u.email}>
                      <Td>
                        <Link
                          to="/crm/users/$email"
                          params={{ email: u.email }}
                          className="hover:text-teal"
                          dir="ltr"
                        >
                          {u.email}
                        </Link>
                      </Td>
                      <Td className="tabular-nums">{num(u.view)}</Td>
                      <Td className="tabular-nums">{num(u.download)}</Td>
                      <Td className="tabular-nums">{num(u.search)}</Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
          </div>
        </>
      )}
    </AppShell>
  );
}
