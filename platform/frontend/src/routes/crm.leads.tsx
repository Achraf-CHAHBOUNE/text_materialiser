import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus, UserCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, Select, STATUS_TONE, Table, Td, TextField } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { convertLead, createLead, leads, updateLead, type Lead } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/leads")({
  head: () => ({ meta: [{ title: "Leads · CRM" }] }),
  component: Leads,
});

const STATUSES = ["new", "contacted", "qualified", "converted", "rejected"];

function Leads() {
  const { t, status } = useI18n();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const list = useQuery({ queryKey: ["leads", filter, q], queryFn: () => leads({ status: filter, q }) });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["leads"] });
  const change = useMutation({ mutationFn: (x: { id: number; status: string }) => updateLead(x.id, { status: x.status }), onSuccess: refresh });
  const convert = useMutation({
    mutationFn: (l: Lead) => convertLead(l.id, { trial: true, invite: true }),
    onSuccess: (r) => { toast.success(t("crm.converted")); refresh(); navigate({ to: "/crm/orgs/$orgId", params: { orgId: String(r.org.id) } }); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <AppShell title={t("crm.leads")} description={t("crm.leadsSubtitle")}
              action={<Button size="sm" onClick={() => setAdding(true)}><Plus className="size-4" />{t("crm.newLead")}</Button>}>
      <CrmNav />
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("crm.searchLeads")} className="h-10 max-w-xs" aria-label={t("crm.searchLeads")} />
          <Select value={filter} onChange={setFilter} label={t("adm.colStatus")}
                  options={[{ value: "", label: t("sup.all") }, ...STATUSES.map((s) => ({ value: s, label: status(s) }))]} />
        </div>
        {list.data && list.data.length === 0 ? <Empty>{t("crm.noLeads")}</Empty> : (
          <Table head={[t("pub.name"), t("pub.company"), t("crm.contact"), t("crm.source"), t("crm.received"), t("adm.colStatus"), ""]} minWidth="56rem">
            {(list.data ?? []).map((l) => (
              <tr key={l.id}>
                <Td className="font-medium">{l.full_name}{l.message && <p className="mt-1 line-clamp-2 max-w-xs text-xs font-normal text-muted-foreground">{l.message}</p>}</Td>
                <Td>{l.company || "—"}<p className="text-xs text-muted-foreground">{l.city}</p></Td>
                <Td><span dir="ltr" className="block">{l.email}</span><span dir="ltr" className="text-xs text-muted-foreground">{l.phone}</span></Td>
                <Td>{t(`src.${l.source}` as "src.website")}</Td>
                <Td className="text-xs">{day(l.created_at)}</Td>
                <Td>
                  {l.status === "converted" ? <Badge tone="good">{status("converted")}</Badge> : (
                    <Select value={l.status} onChange={(s) => change.mutate({ id: l.id, status: s })} className="h-8 text-xs" label={t("adm.colStatus")}
                            options={STATUSES.filter((s) => s !== "converted").map((s) => ({ value: s, label: status(s) }))} />
                  )}
                </Td>
                <Td>
                  {l.org_id ? (
                    <Button size="sm" variant="ghost" onClick={() => navigate({ to: "/crm/orgs/$orgId", params: { orgId: String(l.org_id) } })}>{t("crm.open")}</Button>
                  ) : l.status !== "rejected" && (
                    <Button size="sm" onClick={() => { if (window.confirm(t("crm.convertConfirm"))) convert.mutate(l); }} disabled={convert.isPending}>
                      <UserCheck className="size-4" />{t("crm.convert")}
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <NewLead open={adding} onClose={() => setAdding(false)} onDone={refresh} />
    </AppShell>
  );
}

function NewLead({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { t, lang } = useI18n();
  const blank = { full_name: "", email: "", phone: "", company: "", city: "", message: "", source: "phone" };
  const [f, setF] = useState(blank);
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v });
  const save = useMutation({
    mutationFn: () => createLead({ ...f, language: lang }),
    onSuccess: () => { setF(blank); onDone(); onClose(); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("crm.newLead")}</DialogTitle></DialogHeader>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <TextField label={t("pub.name")} value={f.full_name} onChange={set("full_name")} required />
          <TextField label={t("pub.company")} value={f.company} onChange={set("company")} />
          <TextField label={t("adm.colEmail")} value={f.email} onChange={set("email")} type="email" dir="ltr" />
          <TextField label={t("pub.phone")} value={f.phone} onChange={set("phone")} dir="ltr" />
          <TextField label={t("col.city")} value={f.city} onChange={set("city")} />
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">{t("crm.source")}</p>
            <Select value={f.source} onChange={set("source")} className="w-full"
                    options={["phone", "event", "referral", "website", "other"].map((s) => ({ value: s, label: t(`src.${s}` as "src.website") }))} />
          </div>
          <div className="sm:col-span-2"><TextField label={t("pub.message")} value={f.message} onChange={set("message")} /></div>
          <Button type="submit" className="sm:col-span-2" disabled={save.isPending}>{t("adm.create")}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
