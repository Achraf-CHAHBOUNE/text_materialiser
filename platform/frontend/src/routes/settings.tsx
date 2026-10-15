import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Languages, LogOut, Moon, Sun } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "الإعدادات · Paramètres" }] }),
  component: Settings,
});

function Settings() {
  const navigate = useNavigate();
  const { email, role, theme, toggleTheme, logout } = useStore();
  const { t, lang, setLang } = useI18n();
  return (
    <AppShell title={t("settings.title")} description={t("settings.subtitle")}>
      <div className="max-w-lg space-y-4">
        <div className="rounded-2xl border bg-card p-5 shadow-soft">
          <h2 className="text-sm font-semibold">{t("settings.account")}</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-muted-foreground">{t("adm.colEmail")}</dt><dd className="font-medium">{email || "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-muted-foreground">{t("settings.role")}</dt><dd className="font-medium">{t(role === "admin" ? "settings.role.admin" : "settings.role.client")}</dd></div>
          </dl>
        </div>
        <div className="rounded-2xl border bg-card p-5 shadow-soft">
          <h2 className="text-sm font-semibold">{t("settings.appearance")}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="outline" className="h-10" onClick={toggleTheme}>
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
              {theme === "dark" ? t("shell.theme.light") : t("shell.theme.dark")}
            </Button>
            <Button variant="outline" className="h-10" onClick={() => setLang(lang === "ar" ? "fr" : "ar")}>
              <Languages className="size-4" />{t("lang.switch")}
            </Button>
          </div>
        </div>
        <Button variant="outline" className="h-10 text-destructive"
          onClick={() => { logout(); toast.success(t("login.signedOut")); navigate({ to: "/" }); }}>
          <LogOut className="size-4" />{t("nav.signOut")}
        </Button>
      </div>
    </AppShell>
  );
}
