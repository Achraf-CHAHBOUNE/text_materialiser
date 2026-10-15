import { Link, useRouterState } from "@tanstack/react-router";

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** The CRM's own tabs, above every CRM page. */
export function CrmNav() {
  const { t } = useI18n();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const tabs = [
    { to: "/crm", label: t("crm.dashboard"), exact: true },
    { to: "/crm/users", label: t("trk.users") },
    { to: "/crm/usage", label: t("trk.usage") },
    { to: "/crm/leads", label: t("crm.leads") },
    { to: "/crm/orgs", label: t("crm.orgs") },
    { to: "/crm/tasks", label: t("crm.tasks") },
    { to: "/crm/quotes", label: t("quote.title") },
    { to: "/crm/invoices", label: t("bill.invoices") },
    { to: "/crm/reports", label: t("rep.title") },
    { to: "/support", label: t("nav.support") },
  ];
  return (
    <nav className="mb-5 flex flex-wrap gap-1 rounded-xl border bg-card p-1 text-sm" aria-label="CRM">
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
  );
}
