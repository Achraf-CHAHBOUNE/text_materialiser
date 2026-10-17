import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { BellRing, Trash2 } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, Select, Table, Td } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { alerts, deleteAlert, updateAlert } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/alerts")({
  head: () => ({ meta: [{ title: "تنبيهاتي · Mes alertes" }] }),
  component: Alerts,
});

function Alerts() {
  const { t, chamber, num } = useI18n();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["alerts"], queryFn: alerts });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["alerts"] });
  const change = useMutation({
    mutationFn: (a: { id: number; active?: boolean; frequency?: string }) => updateAlert(a.id, a),
    onSuccess: refresh,
  });
  const drop = useMutation({ mutationFn: deleteAlert, onSuccess: refresh });
  return (
    <AppShell title={t("alert.title")} description={t("alert.subtitle")}>
      <Card>
        <p className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
          <BellRing className="size-4 text-teal" />
          {t("alert.how")}
        </p>
        {list.data && list.data.length === 0 ? (
          <Empty>{t("alert.empty")}</Empty>
        ) : (
          <Table
            head={[
              t("alert.name"),
              t("alert.criteria"),
              t("alert.frequency"),
              t("alert.lastSent"),
              t("alert.active"),
              "",
            ]}
          >
            {(list.data ?? []).map((a) => (
              <tr key={a.id}>
                <Td className="font-medium">{a.name}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {a.query && <Badge tone="info">« {a.query} »</Badge>}
                    {a.chamber && <Badge>{chamber(a.chamber)}</Badge>}
                    {a.year && <Badge>{num(a.year)}</Badge>}
                    {a.city && <Badge>{a.city}</Badge>}
                    {a.theme && <Badge>{t("listing.theme")}</Badge>}
                  </div>
                </Td>
                <Td>
                  <Select
                    value={a.frequency}
                    onChange={(v) => change.mutate({ id: a.id, frequency: v })}
                    label={t("alert.frequency")}
                    options={[
                      { value: "daily", label: t("alert.daily") },
                      { value: "weekly", label: t("alert.weekly") },
                    ]}
                  />
                </Td>
                <Td>{day(a.last_sent_at)}</Td>
                <Td>
                  <Switch
                    checked={a.active}
                    onCheckedChange={(v) => change.mutate({ id: a.id, active: v })}
                    aria-label={t("alert.active")}
                  />
                </Td>
                <Td>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => drop.mutate(a.id)}
                    aria-label={t("lib.delete")}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </AppShell>
  );
}
