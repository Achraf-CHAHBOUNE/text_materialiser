import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { FileCheck2, FolderOpen, Layers, Users } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useStore } from "@/lib/app-store";
import { adminStats } from "@/lib/api";

export const Route = createFileRoute("/dashboard")({
  head: () => ({ meta: [{ title: "Dashboard — القرارات" }] }),
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
  const { isAdmin, email, categories } = useStore();
  const [stats, setStats] = useState<{ decisions: number; published: number; pending: number; clients: number } | null>(null);

  useEffect(() => {
    if (isAdmin) adminStats().then(setStats).catch(() => {});
  }, [isAdmin]);

  return (
    <AppShell title="Dashboard" description={isAdmin ? "Platform overview" : "Browse anonymized court decisions"}>
      {isAdmin ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon={Layers} label="Decisions" value={stats?.decisions ?? "—"} />
            <Stat icon={FileCheck2} label="Published" value={stats?.published ?? "—"} />
            <Stat icon={FolderOpen} label="Pending review" value={stats?.pending ?? "—"} />
            <Stat icon={Users} label="Clients" value={stats?.clients ?? "—"} />
          </div>
          <div className="mt-6 rounded-2xl border bg-card p-6 shadow-soft">
            <h2 className="text-sm font-semibold">Integration</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Import a pipeline batch, review the work queue, publish decisions, and manage client accounts.
            </p>
            <Link to="/admin" className="mt-4 inline-flex h-10 items-center rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground">
              Open admin console
            </Link>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">Signed in as {email}. Browse published decisions by chamber.</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(categories.length ? categories : ["إدارية", "تجارية", "مدنية", "جنائية", "اجتماعية", "أحوال شخصية", "عقارية"]).map((c) => (
              <Link key={c} to="/results"
                className="font-ar rounded-2xl border bg-card p-5 text-start text-lg shadow-soft transition-colors hover:border-teal/50 hover:bg-teal/5">
                {c}
              </Link>
            ))}
          </div>
          <Link to="/results" className="mt-6 inline-flex h-10 items-center rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground">
            Browse all decisions
          </Link>
        </>
      )}
    </AppShell>
  );
}
