import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowDownWideNarrow, Download } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, Select, Stat, STATUS_TONE, Table, Td, when } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { exportActivity, readers, type ReaderRow } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/users/")({
  head: () => ({ meta: [{ title: "Utilisateurs · CRM" }] }),
  component: Readers,
});

const SORTS: Record<string, (a: ReaderRow, b: ReaderRow) => number> = {
  last_seen: (a, b) => (b.last_seen || "").localeCompare(a.last_seen || ""),
  reads: (a, b) => b.reads_30d - a.reads_30d,
  downloads: (a, b) => b.downloads_30d - a.downloads_30d,
  paid: (a, b) => b.org_paid - a.org_paid,
  owed: (a, b) => b.org_owed - a.org_owed,
};

function Readers() {
  const { t, lang, num, status } = useI18n();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("last_seen");
  const [show, setShow] = useState("");
  const list = useQuery({ queryKey: ["readers", q], queryFn: () => readers(q) });
  const rows = useMemo(() => {
    let r = [...(list.data ?? [])];
    if (show === "active") r = r.filter((x) => x.reads_30d + x.downloads_30d + x.searches_30d > 0);
    if (show === "idle") r = r.filter((x) => x.reads_30d + x.downloads_30d + x.searches_30d === 0);
    if (show === "lapsed") r = r.filter((x) => x.access !== "ok");
    if (show === "owing") r = r.filter((x) => x.org_owed > 0);
    return r.sort(SORTS[sort]);
  }, [list.data, sort, show]);
  const all = list.data ?? [];
  return (
    <AppShell title={t("trk.users")} description={t("trk.usersSubtitle")}
              action={<Button size="sm" variant="outline" onClick={() => void exportActivity(30).catch(() => toast.error(t("adm.failed")))}>
                <Download className="size-4" />{t("trk.exportAll")}</Button>}>
      <CrmNav />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("trk.readers")} value={num(all.length)} />
        <Stat label={t("trk.active30")} value={num(all.filter((x) => x.reads_30d + x.downloads_30d + x.searches_30d > 0).length)} tone="good" />
        <Stat label={t("trk.reads30")} value={num(all.reduce((a, x) => a + x.reads_30d, 0))}
              hint={`${num(all.reduce((a, x) => a + x.downloads_30d, 0))} ${t("trk.downloads")}`} />
        <Stat label={t("trk.lapsed")} value={num(all.filter((x) => x.access !== "ok").length)} tone="bad" />
      </div>
      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("trk.search")} aria-label={t("trk.search")} className="h-10 max-w-xs" />
          <Select value={show} onChange={setShow} label={t("trk.show")} options={[
            { value: "", label: t("trk.showAll") }, { value: "active", label: t("trk.showActive") },
            { value: "idle", label: t("trk.showIdle") }, { value: "lapsed", label: t("trk.showLapsed") },
            { value: "owing", label: t("trk.showOwing") }]} />
          <span className="ms-auto flex items-center gap-1 text-xs text-muted-foreground"><ArrowDownWideNarrow className="size-4" />
            <Select value={sort} onChange={setSort} label={t("trk.sort")} className="h-9" options={[
              { value: "last_seen", label: t("trk.sortSeen") }, { value: "reads", label: t("trk.sortReads") },
              { value: "downloads", label: t("trk.sortDownloads") }, { value: "paid", label: t("trk.sortPaid") },
              { value: "owed", label: t("trk.sortOwed") }]} /></span>
        </div>
        {rows.length === 0 && list.data ? <Empty>{t("trk.none")}</Empty> : (
          <Table head={[t("trk.reader"), t("acc.subscription"), t("trk.reads30short"), t("trk.downloads"), t("trk.searches"), t("trk.paid"), t("trk.lastSeen")]} minWidth="64rem">
            {rows.map((r) => (
              <tr key={r.email}>
                <Td>
                  <Link to="/crm/users/$email" params={{ email: r.email }} className="font-medium hover:text-teal" dir="ltr">{r.email}</Link>
                  <p className="text-xs text-muted-foreground">{r.full_name || "—"}{r.org_name ? ` · ${r.org_name}` : ""}</p>
                  {r.status === "suspended" && <Badge tone="bad">{status("suspended")}</Badge>}
                </Td>
                <Td>{r.plan || "—"} <Badge tone={STATUS_TONE[r.access]}>{status(r.access)}</Badge>
                  {r.ends_on && <p className="text-xs text-muted-foreground">{t("acc.until")} {day(r.ends_on)}</p>}</Td>
                <Td className="tabular-nums">{num(r.reads_30d)}<p className="text-xs text-muted-foreground">{num(r.reads_total)} {t("trk.inTotal")}</p></Td>
                <Td className="tabular-nums">{num(r.downloads_30d)}</Td>
                <Td className="tabular-nums">{num(r.searches_30d)}</Td>
                <Td className="tabular-nums">{money(r.org_paid, lang)}
                  {r.org_owed > 0 && <p className="text-xs text-destructive">{t("trk.owes")} {money(r.org_owed, lang)}</p>}</Td>
                <Td className="text-xs">{r.last_seen ? when(r.last_seen) : t("trk.never")}
                  {r.sessions > 0 && <p className="text-teal">{t("trk.signedIn")}</p>}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </AppShell>
  );
}
