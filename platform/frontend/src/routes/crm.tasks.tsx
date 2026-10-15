import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Card, day, Empty } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Switch } from "@/components/ui/switch";
import { crmTasks, updateTask } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/crm/tasks")({
  head: () => ({ meta: [{ title: "Tâches · CRM" }] }),
  component: Tasks,
});

function Tasks() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [mine, setMine] = useState(true);
  const list = useQuery({ queryKey: ["tasks", mine], queryFn: () => crmTasks({ mine, open_only: true }) });
  const done = useMutation({ mutationFn: (id: number) => updateTask(id, { done: true }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["tasks"] }); void qc.invalidateQueries({ queryKey: ["crm-dashboard"] }); } });
  const today = new Date().toISOString().slice(0, 10);
  return (
    <AppShell title={t("crm.tasks")} description={t("crm.tasksSubtitle")}>
      <CrmNav />
      <Card action={<label className="flex items-center gap-2 text-sm"><Switch checked={mine} onCheckedChange={setMine} />{t("crm.onlyMine")}</label>}>
        {list.data && list.data.length === 0 ? <Empty>{t("crm.noTasks")}</Empty> : (
          <ul className="divide-y text-sm">
            {(list.data ?? []).map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <input type="checkbox" onChange={() => done.mutate(x.id)} aria-label={x.title} />
                <span className="font-medium">{x.title}</span>
                {x.org_id && <Link to="/crm/orgs/$orgId" params={{ orgId: String(x.org_id) }} className="text-muted-foreground hover:text-teal">{x.org_name}</Link>}
                <span className={cn("ms-auto text-xs", x.due_on < today ? "font-semibold text-destructive" : x.due_on === today ? "text-amber-600" : "text-muted-foreground")}>
                  {day(x.due_on)}{!mine && ` · ${x.assigned_to}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}
