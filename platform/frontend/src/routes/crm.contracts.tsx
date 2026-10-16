import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, Select, Stat, Table, Td } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { contracts, moneyTotals, transfers, type ContractRow } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/contracts")({
  head: () => ({ meta: [{ title: "Contrats et paiements · CRM" }] }),
  component: ContractsPage,
});

/** The same filters the server knows, read on the list already loaded. */
function keep(c: ContractRow, f: string) {
  if (!f) return true;
  if (f === "ending") return c.status === "active" && c.days_left <= 30;
  if (f === "owing") return c.balance > 0 && c.status !== "cancelled";
  return c.status === f;
}

const TONE = { awaiting_payment: "warn", upcoming: "info", active: "good", ended: "muted", cancelled: "muted", unassigned: "muted" } as const;

/** Every contract and every transfer: what is running, what waits for its money,
 *  what ends soon -- and the money as it came in. */
function ContractsPage() {
  const { t, lang, num } = useI18n();
  const [filter, setFilter] = useState("");
  // every contract once; the filters are read here, the totals come from the server
  const all = useQuery({ queryKey: ["contracts"], queryFn: () => contracts() });
  const tx = useQuery({ queryKey: ["transfers"], queryFn: transfers }).data ?? [];
  const totals = useQuery({ queryKey: ["money"], queryFn: moneyTotals }).data;
  const every = useMemo(() => all.data ?? [], [all.data]);
  const rows = useMemo(() => every.filter((c) => keep(c, filter)), [every, filter]);
  return (
    <AppShell title={t("con.title")} description={t("con.subtitle")}>
      <CrmNav />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("dash.receivedMonth")} value={totals ? money(totals.received_month, lang) : "—"} tone="good"
              hint={totals ? `${t("dash.year")} ${money(totals.received_year, lang)}` : undefined} />
        <Stat label={t("dash.owed")} value={totals ? money(totals.owed, lang) : "—"} tone={totals?.owed ? "bad" : "default"} />
        <Stat label={t("con.st.awaiting_payment")} value={num(every.filter((c) => c.status === "awaiting_payment").length)} tone="warn" />
        <Stat label={t("con.showEnding")} value={num(every.filter((c) => c.status === "active" && c.days_left <= 30).length)} />
      </div>
      <Tabs defaultValue="contracts">
        <TabsList>
          <TabsTrigger value="contracts">{t("con.contracts")}</TabsTrigger>
          <TabsTrigger value="transfers">{t("con.transfers")}</TabsTrigger>
        </TabsList>
        <TabsContent value="contracts" className="mt-4">
          <Card action={<Select value={filter} onChange={setFilter} label={t("trk.show")} options={[
            { value: "", label: t("trk.showAll") }, { value: "awaiting_payment", label: t("con.st.awaiting_payment") },
            { value: "active", label: t("con.st.active") }, { value: "ending", label: t("con.showEnding") },
            { value: "owing", label: t("trk.showOwing") }, { value: "ended", label: t("con.st.ended") }]} />}>
            {all.data && rows.length === 0 ? <Empty>{t("con.none")}</Empty> : (
              <Table head={[t("bill.number"), t("crm.client"), t("con.period"), t("con.accounts"), t("con.price"), t("con.received"), t("adm.colStatus")]} minWidth="60rem">
                {rows.map((c) => (
                  <tr key={c.id}>
                    <Td><span className="font-mono text-xs" dir="ltr">{c.number}</span>{c.has_file ? "" : <p className="text-xs text-amber-700 dark:text-amber-300">{t("con.noFile")}</p>}</Td>
                    <Td><Link to="/crm/orgs/$orgId" params={{ orgId: String(c.org_id) }} className="hover:text-teal">{c.org_name}</Link></Td>
                    <Td className="text-xs">{day(c.starts_on)} → {day(c.ends_on)}{c.status === "active" && <p className="text-muted-foreground">{num(c.days_left)} {t("crm.days")}</p>}</Td>
                    <Td className="tabular-nums">{num(c.seats)}</Td>
                    <Td className="tabular-nums">{money(c.amount_ttc, lang)}</Td>
                    <Td className="tabular-nums">{money(c.received, lang)}{c.balance > 0 && <p className="text-xs text-destructive">{t("trk.owes")} {money(c.balance, lang)}</p>}</Td>
                    <Td><Badge tone={TONE[c.status]}>{t(`con.st.${c.status}` as "con.st.active")}</Badge></Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </TabsContent>
        <TabsContent value="transfers" className="mt-4">
          <Card>
            {tx.length === 0 ? <Empty>{t("con.noTransfers")}</Empty> : (
              <Table head={[t("con.paidOn"), t("crm.client"), t("bill.amount"), t("con.bankRef"), t("con.contract"), ""]} minWidth="50rem">
                {tx.map((x) => (
                  <tr key={x.id}>
                    <Td>{day(x.paid_on)}</Td>
                    <Td><Link to="/crm/orgs/$orgId" params={{ orgId: String(x.org_id) }} className="hover:text-teal">{x.org_name}</Link></Td>
                    <Td className="tabular-nums font-medium">{money(x.amount, lang)}</Td>
                    <Td className="text-xs">{x.bank}{x.bank && x.bank_ref ? " · " : ""}<span dir="ltr">{x.bank_ref}</span></Td>
                    <Td><span className="font-mono text-xs" dir="ltr">{x.contract_number}</span></Td>
                    <Td className="text-xs">{x.has_proof ? <Badge tone="good">{t("con.proof")}</Badge> : <span className="text-muted-foreground">{t("con.noProof")}</span>}
                      {x.invoice_id && <Link to="/invoice/$invoiceId" params={{ invoiceId: String(x.invoice_id) }} className="ms-2 text-teal underline">{t("bill.invoice")}</Link>}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}
