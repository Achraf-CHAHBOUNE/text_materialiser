import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, Select, Table, Td, TextField } from "@/components/biz";
import { CabinetNav } from "@/components/cabinet";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { createMatter, firmMembers, matters, pClients } from "@/lib/api-practice";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/cabinet/matters/")({
  head: () => ({ meta: [{ title: "الملفات · Dossiers" }] }),
  component: Matters,
});

function Matters() {
  const { t, level } = useI18n();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("open");
  const [who, setWho] = useState("");
  const [adding, setAdding] = useState(false);
  const members = useQuery({ queryKey: ["firm-members"], queryFn: firmMembers });
  const list = useQuery({ queryKey: ["matters", q, status, who], queryFn: () => matters({ q, status, responsible: who }) });
  const today = new Date().toISOString().slice(0, 10);
  return (
    <AppShell title={t("cab.matters")} description={t("cab.mattersSubtitle")}
              action={<Button size="sm" onClick={() => setAdding(true)}><Plus className="size-4" />{t("cab.newMatter")}</Button>}>
      <CabinetNav />
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("cab.searchMatters")} aria-label={t("cab.searchMatters")} className="h-10 max-w-sm" />
          <Select value={status} onChange={setStatus} label={t("adm.colStatus")}
                  options={[{ value: "open", label: t("cab.status.open") }, { value: "closed", label: t("cab.status.closed") },
                    { value: "archived", label: t("cab.status.archived") }, { value: "", label: t("sup.all") }]} />
          <Select value={who} onChange={setWho} label={t("cab.responsible")}
                  options={[{ value: "", label: t("cab.everyone") }, ...(members.data ?? []).map((m) => ({ value: m.email, label: m.full_name || m.email }))]} />
        </div>
        {list.data && list.data.length === 0 ? <Empty>{t("cab.noMatters")}</Empty> : (
          <Table head={[t("cab.reference"), t("cab.matter"), t("cab.client"), t("cab.court"), t("cab.nextHearing"), t("cab.nextDeadline")]} minWidth="60rem">
            {(list.data ?? []).map((m) => (
              <tr key={m.id}>
                <Td><span className="font-mono text-xs" dir="ltr">{m.reference}</span></Td>
                <Td><Link to="/cabinet/matters/$matterId" params={{ matterId: String(m.id) }} className="font-medium hover:text-teal">{m.title}</Link>
                  {m.case_number && <p className="text-xs text-muted-foreground">{t("col.fileNo")} <span dir="ltr">{m.case_number}</span></p>}</Td>
                <Td>{m.client_name || "—"}</Td>
                <Td>{m.court || "—"}{m.level && <p className="text-xs text-muted-foreground">{level(m.level)}</p>}</Td>
                <Td>{m.next_hearing ? day(m.next_hearing) : "—"}</Td>
                <Td>{m.next_deadline ? <Badge tone={m.next_deadline < today ? "bad" : "warn"}>{day(m.next_deadline)}</Badge> : "—"}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <NewMatter open={adding} onClose={() => setAdding(false)} />
    </AppShell>
  );
}

function NewMatter({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, level } = useI18n();
  const navigate = useNavigate();
  const clients = useQuery({ queryKey: ["p-clients", ""], queryFn: () => pClients(""), enabled: open });
  const blank = { title: "", client_id: "", court: "", level: "ابتدائي", case_number: "", opposing_party: "", kind: "" };
  const [f, setF] = useState(blank);
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v });
  const save = useMutation({
    mutationFn: () => createMatter({ ...f, client_id: f.client_id ? Number(f.client_id) : null, level: f.level as "ابتدائي" }),
    onSuccess: (m) => { setF(blank); onClose(); navigate({ to: "/cabinet/matters/$matterId", params: { matterId: String(m.id) } }); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("cab.newMatter")}</DialogTitle></DialogHeader>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="sm:col-span-2"><TextField label={t("cab.matterTitle")} value={f.title} onChange={set("title")} required /></div>
          <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("cab.client")}</p>
            <Select value={f.client_id} onChange={set("client_id")} className="w-full"
                    options={[{ value: "", label: "—" }, ...(clients.data ?? []).map((c) => ({ value: String(c.id), label: c.full_name }))]} /></div>
          <TextField label={t("cab.opposing")} value={f.opposing_party} onChange={set("opposing_party")} />
          <TextField label={t("cab.court")} value={f.court} onChange={set("court")} />
          <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("col.level")}</p>
            <Select value={f.level} onChange={set("level")} className="w-full"
                    options={["ابتدائي", "استئناف", "نقض"].map((l) => ({ value: l, label: level(l) }))} /></div>
          <TextField label={t("col.fileNo")} value={f.case_number} onChange={set("case_number")} dir="ltr" />
          <TextField label={t("cab.kindOfCase")} value={f.kind} onChange={set("kind")} />
          <Button type="submit" className="sm:col-span-2" disabled={save.isPending}>{t("adm.create")}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
