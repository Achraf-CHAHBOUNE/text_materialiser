import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, STATUS_TONE, Table, Td, TextField } from "@/components/biz";
import { CabinetNav } from "@/components/cabinet";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { createMatter, erasePClient, pClient, updatePClient, type PClient } from "@/lib/api-practice";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/cabinet/clients/$clientId")({
  component: ClientPage,
});

function ClientPage() {
  const { clientId } = Route.useParams();
  const id = Number(clientId);
  const { t, lang, status } = useI18n();
  const { isClientAdmin } = useStore();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const c = useQuery({ queryKey: ["p-client", id], queryFn: () => pClient(id) });
  const erase = useMutation({
    mutationFn: () => erasePClient(id),
    onSuccess: (r) => { toast.success(`${t("cab.erased")} (${r.matters} · ${r.files})`); void qc.invalidateQueries({ queryKey: ["p-clients"] }); navigate({ to: "/cabinet/clients" }); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  const open = useMutation({
    mutationFn: () => createMatter({ title: c.data?.full_name ?? "", client_id: id }),
    onSuccess: (m) => navigate({ to: "/cabinet/matters/$matterId", params: { matterId: String(m.id) } }),
  });
  const d = c.data;
  return (
    <AppShell title={d?.full_name ?? t("cab.client")} description={d ? t(`cab.kind.${d.kind}` as "cab.kind.person") : ""}
              action={isClientAdmin && d && (
                <Button size="sm" variant="outline" className="text-destructive" onClick={() => {
                  if (window.confirm(t("cab.eraseClientConfirm"))) erase.mutate();
                }}><Trash2 className="size-4" />{t("cab.erase")}</Button>
              )}>
      <CabinetNav />
      {d && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
          <ClientForm key={d.id} c={d} />
          <div className="space-y-4">
            <Card title={t("cab.matters")} action={<Button size="sm" onClick={() => open.mutate()}><Plus className="size-4" />{t("cab.newMatter")}</Button>}>
              {d.matters.length === 0 ? <Empty>{t("cab.noMatters")}</Empty> : (
                <ul className="divide-y text-sm">
                  {d.matters.map((m) => (
                    <li key={m.id} className="flex items-center justify-between gap-2 py-2">
                      <Link to="/cabinet/matters/$matterId" params={{ matterId: String(m.id) }} className="hover:text-teal">
                        <span className="me-2 font-mono text-xs text-muted-foreground" dir="ltr">{m.reference}</span>{m.title}
                      </Link>
                      <Badge tone={STATUS_TONE[m.status === "open" ? "open" : "closed"]}>{t(`cab.status.${m.status}` as "cab.status.open")}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title={t("cab.fees")}>
              {d.fee_invoices.length === 0 ? <Empty>{t("bill.none")}</Empty> : (
                <Table head={[t("bill.number"), t("bill.issued"), t("bill.total"), t("bill.balance"), t("adm.colStatus")]} minWidth="30rem">
                  {d.fee_invoices.map((f) => (
                    <tr key={f.id}>
                      <Td><Link to="/fee/$feeId" params={{ feeId: String(f.id) }} className="font-mono text-teal hover:underline" dir="ltr">{f.number}</Link></Td>
                      <Td>{day(f.issued_on)}</Td><Td className="tabular-nums">{money(f.amount_ttc, lang)}</Td>
                      <Td className="tabular-nums">{money(f.balance, lang)}</Td>
                      <Td><Badge tone={STATUS_TONE[f.status]}>{status(f.status)}</Badge></Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
          </div>
        </div>
      )}
    </AppShell>
  );
}

function ClientForm({ c }: { c: PClient }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [f, setF] = useState({ full_name: c.full_name, cin: c.cin, ice: c.ice, phone: c.phone, email: c.email,
    address: c.address, city: c.city, notes: c.notes });
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v });
  const save = useMutation({
    mutationFn: () => updatePClient(c.id, f),
    onSuccess: () => { toast.success(t("adm.saved")); void qc.invalidateQueries({ queryKey: ["p-client", c.id] }); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <Card title={t("cab.identity")}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextField label={t("pub.name")} value={f.full_name} onChange={set("full_name")} required />
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField label={c.kind === "company" ? t("cab.rc") : t("cab.cin")} value={f.cin} onChange={set("cin")} dir="ltr" />
          {c.kind === "company" && <TextField label="ICE" value={f.ice} onChange={set("ice")} dir="ltr" />}
          <TextField label={t("pub.phone")} value={f.phone} onChange={set("phone")} dir="ltr" />
          <TextField label={t("adm.colEmail")} value={f.email} onChange={set("email")} dir="ltr" />
          <TextField label={t("col.city")} value={f.city} onChange={set("city")} />
        </div>
        <TextField label={t("crm.address")} value={f.address} onChange={set("address")} />
        <Textarea value={f.notes} onChange={(e) => set("notes")(e.target.value)} rows={3} placeholder={t("crm.notes")} aria-label={t("crm.notes")} />
        <Button type="submit" size="sm" disabled={save.isPending}>{t("adm.save")}</Button>
      </form>
    </Card>
  );
}
