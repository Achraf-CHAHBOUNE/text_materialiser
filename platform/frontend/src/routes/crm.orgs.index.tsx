import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, Select, STATUS_TONE, Table, Td } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Input } from "@/components/ui/input";
import { orgs } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/orgs/")({
  head: () => ({ meta: [{ title: "Clients · CRM" }] }),
  component: Clients,
});

function Clients() {
  const { t, lang, num, status } = useI18n();
  const [q, setQ] = useState("");
  const [show, setShow] = useState("");
  const list = useQuery({ queryKey: ["orgs", q], queryFn: () => orgs(q) });
  const rows = useMemo(
    () =>
      (list.data ?? []).filter(
        (o) =>
          !show ||
          (show === "active" && o.access === "ok") ||
          (show === "waiting" && o.contract?.status === "awaiting_payment") ||
          (show === "ending" && o.contract?.status === "active" && o.contract.days_left <= 30) ||
          (show === "ended" && o.access !== "ok" && o.contract?.status !== "awaiting_payment") ||
          (show === "owing" && o.owed > 0),
      ),
    [list.data, show],
  );
  return (
    <AppShell title={t("crm.clients")} description={t("crm.clientsSubtitle")}>
      <CrmNav />
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("crm.searchOrgs")}
            className="h-10 max-w-xs"
            aria-label={t("crm.searchOrgs")}
          />
          <Select
            value={show}
            onChange={setShow}
            label={t("trk.show")}
            options={[
              { value: "", label: t("trk.showAll") },
              { value: "active", label: t("con.showActive") },
              { value: "waiting", label: t("con.st.awaiting_payment") },
              { value: "ending", label: t("con.showEnding") },
              { value: "ended", label: t("con.showEnded") },
              { value: "owing", label: t("trk.showOwing") },
            ]}
          />
        </div>
        {list.data && rows.length === 0 ? (
          <Empty>{t("crm.noOrgs")}</Empty>
        ) : (
          <Table
            head={[
              t("crm.client"),
              t("con.contract"),
              t("con.accounts"),
              t("trk.paid"),
              t("crm.health"),
            ]}
            minWidth="56rem"
          >
            {rows.map((o) => (
              <tr key={o.id}>
                <Td>
                  <Link
                    to="/crm/orgs/$orgId"
                    params={{ orgId: String(o.id) }}
                    className="font-medium hover:text-teal"
                  >
                    {o.name}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {t(`kind.${o.kind}` as "kind.firm")}
                    {o.city ? ` · ${o.city}` : ""}
                  </p>
                </Td>
                <Td>
                  {o.contract ? (
                    <>
                      <Badge
                        tone={
                          o.contract.status === "awaiting_payment"
                            ? "warn"
                            : o.access === "ok"
                              ? "good"
                              : "muted"
                        }
                      >
                        {t(`con.st.${o.contract.status}` as "con.st.active")}
                      </Badge>
                      <p className="text-xs text-muted-foreground">
                        {day(o.contract.starts_on)} → {day(o.contract.ends_on)}
                      </p>
                    </>
                  ) : (
                    <Badge tone="muted">{status("none")}</Badge>
                  )}
                </Td>
                <Td className="tabular-nums">
                  {num(o.seats.used)} / {num(o.contract?.seats ?? o.seats.total)}
                </Td>
                <Td className="tabular-nums">
                  {money(o.paid, lang)}
                  {o.owed > 0 && (
                    <p className="text-xs text-destructive">
                      {t("trk.owes")} {money(o.owed, lang)}
                    </p>
                  )}
                </Td>
                <Td>
                  <Badge tone={STATUS_TONE[o.health]}>{status(o.health)}</Badge>
                  <p className="text-xs text-muted-foreground">
                    {num(o.activity_30d)} {t("crm.actions30")}
                  </p>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </AppShell>
  );
}
