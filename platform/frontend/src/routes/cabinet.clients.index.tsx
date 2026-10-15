import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Card, Empty, Select, Table, Td, TextField } from "@/components/biz";
import { CabinetNav } from "@/components/cabinet";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { createPClient, pClients } from "@/lib/api-practice";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/cabinet/clients/")({
  head: () => ({ meta: [{ title: "الموكلون · Clients" }] }),
  component: Clients,
});

function Clients() {
  const { t, num } = useI18n();
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const list = useQuery({ queryKey: ["p-clients", q], queryFn: () => pClients(q) });
  return (
    <AppShell title={t("cab.clients")} description={t("cab.clientsSubtitle")}
              action={<Button size="sm" onClick={() => setAdding(true)}><Plus className="size-4" />{t("cab.newClient")}</Button>}>
      <CabinetNav />
      <Card>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("cab.searchClients")} aria-label={t("cab.searchClients")} className="mb-3 h-10 max-w-sm" />
        {list.data && list.data.length === 0 ? <Empty>{t("cab.noClients")}</Empty> : (
          <Table head={[t("pub.name"), t("cab.cin"), t("pub.phone"), t("col.city"), t("cab.openMatters")]}>
            {(list.data ?? []).map((c) => (
              <tr key={c.id}>
                <Td><Link to="/cabinet/clients/$clientId" params={{ clientId: String(c.id) }} className="font-medium hover:text-teal">{c.full_name}</Link>
                  <p className="text-xs text-muted-foreground">{t(`cab.kind.${c.kind}` as "cab.kind.person")}</p></Td>
                <Td><span dir="ltr">{c.cin || "—"}</span></Td>
                <Td><span dir="ltr">{c.phone || "—"}</span></Td>
                <Td>{c.city || "—"}</Td>
                <Td className="tabular-nums">{num(c.open_matters ?? 0)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <p className="mt-3 text-xs text-muted-foreground">{t("cab.privacy")}</p>
      <NewClient open={adding} onClose={() => setAdding(false)} />
    </AppShell>
  );
}

function NewClient({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const blank = { kind: "person", full_name: "", cin: "", phone: "", email: "", address: "", city: "" };
  const [f, setF] = useState(blank);
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v });
  const save = useMutation({
    mutationFn: () => createPClient({ ...f, kind: f.kind as "person" | "company" }),
    onSuccess: (c) => { setF(blank); void qc.invalidateQueries({ queryKey: ["p-clients"] }); onClose();
      navigate({ to: "/cabinet/clients/$clientId", params: { clientId: String(c.id) } }); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("cab.newClient")}</DialogTitle></DialogHeader>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("crm.kind")}</p>
            <Select value={f.kind} onChange={set("kind")} className="w-full"
                    options={[{ value: "person", label: t("cab.kind.person") }, { value: "company", label: t("cab.kind.company") }]} /></div>
          <TextField label={t("pub.name")} value={f.full_name} onChange={set("full_name")} required />
          <TextField label={f.kind === "company" ? t("cab.rc") : t("cab.cin")} value={f.cin} onChange={set("cin")} dir="ltr" />
          <TextField label={t("pub.phone")} value={f.phone} onChange={set("phone")} dir="ltr" />
          <TextField label={t("adm.colEmail")} value={f.email} onChange={set("email")} type="email" dir="ltr" />
          <TextField label={t("col.city")} value={f.city} onChange={set("city")} />
          <div className="sm:col-span-2"><TextField label={t("crm.address")} value={f.address} onChange={set("address")} /></div>
          <Button type="submit" className="sm:col-span-2" disabled={save.isPending}>{t("adm.create")}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
