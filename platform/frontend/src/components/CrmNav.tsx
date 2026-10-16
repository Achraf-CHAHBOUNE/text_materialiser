import { Link, useRouterState } from "@tanstack/react-router";
import { UserPlus } from "lucide-react";

import { FindFile } from "@/components/FindFile";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** The CRM's tabs, the "new client" button, and the box that traces a file. */
export function CrmNav() {
  const { t } = useI18n();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const tabs = [
    { to: "/crm", label: t("crm.dashboard"), exact: true },
    { to: "/crm/orgs", label: t("crm.clients") },
    { to: "/crm/users", label: t("trk.users") },
    { to: "/crm/usage", label: t("trk.usage") },
    { to: "/crm/alerts", label: t("crm.alerts") },
    { to: "/crm/contracts", label: t("con.title") },
    { to: "/support", label: t("nav.support") },
  ];
  return (
    <div className="mb-5 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <nav className="flex flex-1 flex-wrap gap-1 rounded-xl border bg-card p-1 text-sm" aria-label="CRM">
          {tabs.map((x) => {
            const on = x.exact ? path === x.to || path === `${x.to}/` : path.startsWith(x.to);
            return (
              <Link key={x.to} to={x.to}
                    className={cn("rounded-lg px-3 py-1.5 transition-colors",
                      on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground")}>
                {x.label}
              </Link>
            );
          })}
        </nav>
        <Link to="/crm/new" className="inline-flex h-10 items-center gap-2 rounded-xl bg-teal px-4 text-sm font-medium text-white shadow-sm hover:opacity-90">
          <UserPlus className="size-4" />{t("con.newClient")}
        </Link>
      </div>
      <FindFile />
    </div>
  );
}
