import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { LifeBuoy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, Empty, Select, STATUS_TONE, Table, Td, TextField, when } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { openTicket, tickets } from "@/lib/api-biz";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/support/")({
  head: () => ({ meta: [{ title: "الدعم · Assistance" }] }),
  component: Support,
});

function Support() {
  const { t, status } = useI18n();
  const { isStaff } = useStore();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [filter, setFilter] = useState(isStaff ? "open" : "");
  const list = useQuery({ queryKey: ["tickets", filter], queryFn: () => tickets(filter) });
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const create = useMutation({
    mutationFn: () => openTicket({ subject, body }),
    onSuccess: (x) => { void qc.invalidateQueries({ queryKey: ["tickets"] }); navigate({ to: "/support/$ticketId", params: { ticketId: String(x.id) } }); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <AppShell title={t("nav.support")} description={isStaff ? t("sup.staffSubtitle") : t("sup.subtitle")}>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card title={t("sup.list")} action={
          <Select value={filter} onChange={setFilter} label={t("adm.colStatus")} options={[
            { value: "", label: t("sup.all") }, { value: "open", label: status("open") },
            { value: "pending", label: status("pending") }, { value: "closed", label: status("closed") }]} />
        }>
          {list.data && list.data.length === 0 ? <Empty>{t("sup.empty")}</Empty> : (
            <Table head={[t("sup.subject"), ...(isStaff ? [t("crm.org")] : []), t("adm.colStatus"), t("sup.updated")]} minWidth="30rem">
              {(list.data ?? []).map((x) => (
                <tr key={x.id}>
                  <Td>
                    <Link to="/support/$ticketId" params={{ ticketId: String(x.id) }} className="font-medium hover:text-teal">{x.subject}</Link>
                    <p className="text-xs text-muted-foreground">{x.user_email}</p>
                  </Td>
                  {isStaff && <Td>{x.org_name || "—"}</Td>}
                  <Td><div className="flex gap-1"><Badge tone={STATUS_TONE[x.status]}>{status(x.status)}</Badge>
                    {x.priority === "high" && <Badge tone="bad">{status("high")}</Badge>}</div></Td>
                  <Td className="text-xs">{when(x.updated_at)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        {!isStaff && (
          <Card title={<span className="flex items-center gap-2"><LifeBuoy className="size-4 text-teal" />{t("sup.new")}</span>}>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
              <TextField label={t("sup.subject")} value={subject} onChange={setSubject} required />
              <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} required
                        placeholder={t("sup.describe")} aria-label={t("sup.describe")} />
              <Button type="submit" className="w-full" disabled={create.isPending}>{t("pub.send")}</Button>
            </form>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
