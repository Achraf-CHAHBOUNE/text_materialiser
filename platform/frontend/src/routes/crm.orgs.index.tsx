import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, Select, STATUS_TONE, Table, Td, TextField } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { createOrg, orgs } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/orgs/")({
  head: () => ({ meta: [{ title: "Organisations · CRM" }] }),
  component: Orgs,
});

const KINDS = ["firm", "company", "institution", "individual"];

function Orgs() {
  const { t, lang, num, status } = useI18n();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("");
  const [adding, setAdding] = useState(false);
  const list = useQuery({ queryKey: ["orgs", q, filter], queryFn: () => orgs({ q, status: filter }) });
  return (
    <AppShell title={t("crm.orgs")} description={t("crm.orgsSubtitle")}
              action={<Button size="sm" onClick={() => setAdding(true)}><Plus className="size-4" />{t("crm.newOrg")}</Button>}>
      <CrmNav />
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("crm.searchOrgs")} className="h-10 max-w-xs" aria-label={t("crm.searchOrgs")} />
          <Select value={filter} onChange={setFilter} label={t("adm.colStatus")}
                  options={[{ value: "", label: t("sup.all") }, ...["prospect", "customer", "former"].map((s) => ({ value: s, label: status(s) }))]} />
        </div>
        {list.data && list.data.length === 0 ? <Empty>{t("crm.noOrgs")}</Empty> : (
          <Table head={[t("crm.org"), t("adm.colStatus"), t("acc.subscription"), t("pub.seats"), t("crm.health"), t("crm.manager")]} minWidth="56rem">
            {(list.data ?? []).map((o) => (
              <tr key={o.id}>
                <Td>
                  <Link to="/crm/orgs/$orgId" params={{ orgId: String(o.id) }} className="font-medium hover:text-teal">{o.name}</Link>
                  <p className="text-xs text-muted-foreground">{t(`kind.${o.kind}` as "kind.firm")}{o.city ? ` · ${o.city}` : ""}</p>
                </Td>
                <Td><Badge tone={STATUS_TONE[o.status]}>{status(o.status)}</Badge></Td>
                <Td>
                  {o.subscription ? (
                    <>
                      <span>{lang === "fr" ? o.subscription.plan_name_fr : o.subscription.plan_name_ar}</span>{" "}
                      <Badge tone={STATUS_TONE[o.access === "ok" ? o.subscription.status : o.access]}>
                        {status(o.access === "ok" ? o.subscription.status : o.access)}
                      </Badge>
                      <p className="text-xs text-muted-foreground">{t("acc.until")} {day(o.subscription.ends_on)}</p>
                    </>
                  ) : "—"}
                </Td>
                <Td className="tabular-nums">{num(o.seats_used)} / {num(o.subscription?.seats ?? 0)}</Td>
                <Td><Badge tone={STATUS_TONE[o.health]}>{status(o.health)}</Badge>
                  <p className="text-xs text-muted-foreground">{num(o.activity_30d)} {t("crm.actions30")}</p></Td>
                <Td className="text-xs">{o.account_manager || "—"}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <NewOrg open={adding} onClose={() => setAdding(false)} />
    </AppShell>
  );
}

function NewOrg({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [f, setF] = useState({ name: "", kind: "firm", city: "", email: "", phone: "", ice: "" });
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v });
  const save = useMutation({
    mutationFn: () => createOrg({ ...f, language: lang }),
    onSuccess: (o) => { void qc.invalidateQueries({ queryKey: ["orgs"] }); onClose(); navigate({ to: "/crm/orgs/$orgId", params: { orgId: String(o.id) } }); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("crm.newOrg")}</DialogTitle></DialogHeader>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <TextField label={t("crm.orgName")} value={f.name} onChange={set("name")} required />
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">{t("crm.kind")}</p>
            <Select value={f.kind} onChange={set("kind")} className="w-full"
                    options={KINDS.map((k) => ({ value: k, label: t(`kind.${k}` as "kind.firm") }))} />
          </div>
          <TextField label={t("col.city")} value={f.city} onChange={set("city")} />
          <TextField label="ICE" value={f.ice} onChange={set("ice")} dir="ltr" />
          <TextField label={t("adm.colEmail")} value={f.email} onChange={set("email")} type="email" dir="ltr" />
          <TextField label={t("pub.phone")} value={f.phone} onChange={set("phone")} dir="ltr" />
          <Button type="submit" className="sm:col-span-2" disabled={save.isPending}>{t("adm.create")}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
