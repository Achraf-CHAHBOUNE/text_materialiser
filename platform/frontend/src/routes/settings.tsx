import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { LogOut, Moon, Sun } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { useStore } from "@/lib/app-store";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings — القرارات" }] }),
  component: Settings,
});

function Settings() {
  const navigate = useNavigate();
  const { email, role, theme, toggleTheme, logout } = useStore();
  return (
    <AppShell title="Settings" description="Account & preferences">
      <div className="max-w-lg space-y-4">
        <div className="rounded-2xl border bg-card p-5 shadow-soft">
          <h2 className="text-sm font-semibold">Account</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-muted-foreground">Email</dt><dd className="font-medium">{email || "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-muted-foreground">Role</dt><dd className="font-medium capitalize">{role || "client"}</dd></div>
          </dl>
        </div>
        <div className="rounded-2xl border bg-card p-5 shadow-soft">
          <h2 className="text-sm font-semibold">Appearance</h2>
          <Button variant="outline" className="mt-3 h-10" onClick={toggleTheme}>
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </Button>
        </div>
        <Button variant="outline" className="h-10 text-destructive"
          onClick={() => { logout(); toast.success("Signed out"); navigate({ to: "/" }); }}>
          <LogOut className="size-4" />Sign out
        </Button>
      </div>
    </AppShell>
  );
}
