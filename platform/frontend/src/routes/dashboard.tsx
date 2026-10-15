import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { FileCheck2, FolderOpen, Layers, Users } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useI18n } from "@/lib/i18n";
import { useStore } from "@/lib/app-store";
import { adminStats } from "@/lib/api";

export const Route = createFileRoute("/dashboard")({
  head: () => ({ meta: [{ title: "لوحة القيادة · Tableau de bord" }] }),
  component: Dashboard,
});

function Stat({ icon: Icon, label, value }: { icon: any; label: string; value: number | string }) {
  return (
    <div className="rounded-2xl border bg-card p-5 shadow-soft">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-teal/10 text-teal">
          <Icon className="size-5" />
        </span>
        <div>
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </div>
    </div>
  );
}

function Dashboard() {
  const { t, num, chamber: chamberName } = useI18n();
  const { isAdmin, email, categories } = useStore();
  const [stats, setStats] = useState<{ decisions: number; published: number; pending: number; clients: number } | null>(null);

  useEffect(() => {
    if (isAdmin) adminStats().then(setStats).catch(() => {});
  }, [isAdmin]);

  return (
    <AppShell title={t("dash.title")} description={isAdmin ? t("dash.overview") : t("dash.forClient")}>
      {isAdmin ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon={Layers} label={t("dash.decisions")} value={stats ? num(stats.decisions) : "—"} />
            <Stat icon={FileCheck2} label={t("dash.published")} value={stats ? num(stats.published) : "—"} />
            <Stat icon={FolderOpen} label={t("dash.pending")} value={stats ? num(stats.pending) : "—"} />
            <Stat icon={Users} label={t("dash.clients")} value={stats ? num(stats.clients) : "—"} />
          </div>
          <div className="mt-6 rounded-2xl border bg-card p-6 shadow-soft">
            <h2 className="text-sm font-semibold">{t("dash.integration")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("dash.adminHint")}</p>
            <Link to="/admin" className="mt-4 inline-flex h-10 items-center rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground">
              {t("dash.openAdmin")}
            </Link>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">{t("dash.signedInAs")} {email}. {t("dash.byChamber")}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(categories.length ? categories : ["إدارية", "تجارية", "مدنية", "جنائية", "اجتماعية", "أحوال شخصية", "عقارية"]).map((c) => (
              <Link key={c} to="/browse/$chamber" params={{ chamber: c }}
                className="font-ar rounded-2xl border bg-card p-5 text-start text-lg shadow-soft transition-colors hover:border-teal/50 hover:bg-teal/5">
                {chamberName(c)}
              </Link>
            ))}
          </div>
          <Link to="/browse" className="mt-6 inline-flex h-10 items-center rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground">
            {t("dash.browseAll")}
          </Link>
        </>
      )}
    </AppShell>
  );
}
