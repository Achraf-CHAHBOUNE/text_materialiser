import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, Select, STATUS_TONE, when } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { replyTicket, ticket, updateTicket } from "@/lib/api-biz";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/support/$ticketId")({
  component: TicketPage,
});

function TicketPage() {
  const { ticketId } = Route.useParams();
  const id = Number(ticketId);
  const { t, status } = useI18n();
  const { isStaff } = useStore();
  const qc = useQueryClient();
  const x = useQuery({ queryKey: ["ticket", id], queryFn: () => ticket(id) });
  const [body, setBody] = useState("");
  const set = (data: unknown) => {
    qc.setQueryData(["ticket", id], data);
    void qc.invalidateQueries({ queryKey: ["tickets"] });
  };
  const reply = useMutation({
    mutationFn: () => replyTicket(id, body),
    onSuccess: (d) => {
      set(d);
      setBody("");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  const change = useMutation({
    mutationFn: (b: { status?: string; priority?: string }) => updateTicket(id, b),
    onSuccess: set,
  });
  const d = x.data;
  return (
    <AppShell
      title={d?.subject ?? t("nav.support")}
      description={d ? `${d.org_name || d.user_email}` : ""}
      action={
        d && (
          <div className="flex items-center gap-2">
            <Badge tone={STATUS_TONE[d.status]}>{status(d.status)}</Badge>
            {isStaff ? (
              <>
                <Select
                  value={d.status}
                  onChange={(v) => change.mutate({ status: v })}
                  label={t("adm.colStatus")}
                  options={["open", "pending", "closed"].map((v) => ({
                    value: v,
                    label: status(v),
                  }))}
                />
                <Select
                  value={d.priority}
                  onChange={(v) => change.mutate({ priority: v })}
                  label={t("sup.priority")}
                  options={["normal", "high"].map((v) => ({ value: v, label: status(v) }))}
                />
              </>
            ) : (
              d.status !== "closed" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => change.mutate({ status: "closed" })}
                >
                  {t("sup.close")}
                </Button>
              )
            )}
          </div>
        )
      }
    >
      <p className="mb-3 text-sm">
        <Link to="/support" className="text-muted-foreground hover:text-foreground">
          ← {t("sup.list")}
        </Link>
      </p>
      <div className="space-y-3">
        {(d?.messages ?? []).map((m) => (
          <div
            key={m.id}
            className={cn(
              "max-w-3xl rounded-2xl border p-4",
              m.staff ? "ms-auto bg-teal/5" : "bg-card",
            )}
          >
            <p className="text-xs text-muted-foreground">
              {m.staff ? t("sup.team") : m.author} · {when(m.created_at)}
            </p>
            <p className="mt-1 whitespace-pre-wrap text-sm">{m.body}</p>
          </div>
        ))}
      </div>
      {d && (
        <Card className="mt-4 max-w-3xl">
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              reply.mutate();
            }}
          >
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              required
              placeholder={t("sup.reply")}
              aria-label={t("sup.reply")}
            />
            <Button type="submit" disabled={reply.isPending}>
              {t("pub.send")}
            </Button>
          </form>
        </Card>
      )}
    </AppShell>
  );
}
