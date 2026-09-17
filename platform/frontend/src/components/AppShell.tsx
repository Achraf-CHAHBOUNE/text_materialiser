import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  LogOut,
  ListChecks,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Scale,
  ScrollText,
  ShieldCheck,
  Sun,
  User,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { BrandMark, Wordmark } from "@/components/Brand";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export { Wordmark, BrandMark };

function useNav() {
  const { isAdmin } = useStore();
  const { t } = useI18n();
  const items = [
    { to: "/browse", label: t("nav.browse"), icon: Scale },
    { to: "/dashboard", label: t("nav.dashboard"), icon: LayoutDashboard },
    { to: "/results", label: t("nav.decisions"), icon: ScrollText },
  ];
  if (isAdmin) {
    items.push({ to: "/corrections", label: t("nav.review"), icon: ListChecks });
    items.push({ to: "/admin", label: t("nav.admin"), icon: ShieldCheck });
  }
  return items;
}

function NavList({ onNavigate, collapsed }: { onNavigate?: () => void; collapsed?: boolean }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const items = useNav();
  return (
    <nav className="flex flex-col gap-1" aria-label="Main">
      {items.map((item) => {
        const active = pathname.startsWith(item.to);
        const link = (
          <Link
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={cn(
              "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
              collapsed && "justify-center px-0",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-xs"
                : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
            )}
            aria-current={active ? "page" : undefined}
          >
            {active && <span aria-hidden className="absolute inset-y-1.5 start-0 w-1 rounded-full bg-teal" />}
            <item.icon className={cn("size-4.5 shrink-0", active ? "text-teal" : "group-hover:text-foreground")} aria-hidden />
            {!collapsed && item.label}
          </Link>
        );
        return collapsed ? (
          <Tooltip key={item.to}>
            <TooltipTrigger asChild>{link}</TooltipTrigger>
            <TooltipContent side="right">{item.label}</TooltipContent>
          </Tooltip>
        ) : (
          link
        );
      })}
    </nav>
  );
}

function ThemeToggle() {
  const { theme, toggleTheme } = useStore();
  const { t } = useI18n();
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={toggleTheme}
          aria-label={theme === "dark" ? t("shell.theme.light") : t("shell.theme.dark")}
          className="min-h-11 min-w-11 rounded-xl">
          {theme === "dark" ? <Sun className="size-4.5" /> : <Moon className="size-4.5" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{theme === "dark" ? t("shell.theme.light") : t("shell.theme.dark")}</TooltipContent>
    </Tooltip>
  );
}

function LanguageToggle() {
  const { lang, setLang, t } = useI18n();
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          onClick={() => setLang(lang === "ar" ? "fr" : "ar")}
          aria-label={t("lang.switch")}
          className="min-h-11 rounded-xl px-3 text-sm font-medium"
        >
          {lang === "ar" ? "FR" : "ع"}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{t("lang.switch")}</TooltipContent>
    </Tooltip>
  );
}


function AvatarMenu() {
  const navigate = useNavigate();
  const { email, role, logout } = useStore();
  const { t } = useI18n();
  const initials = (email || "?").slice(0, 2).toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={t("shell.accountMenu")}
          className="grid size-10 place-items-center rounded-xl bg-primary text-sm font-semibold text-primary-foreground transition-transform duration-200 hover:scale-105">
          {initials}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="text-sm font-medium">{email || "—"}</span>
          <span className="text-xs font-normal capitalize text-muted-foreground">{role || "client"}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/settings"><User className="size-4" />{t("shell.profile")}</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            logout();
            toast.success(t("login.signedOut"));
            navigate({ to: "/" });
          }}
        >
          <LogOut className="size-4" />
          {t("nav.signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({
  title,
  description,
  action,
  children,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const { t } = useI18n();
  const navigate = useNavigate();
  const { authed, ready, refreshCategories } = useStore();

  useEffect(() => {
    if (!ready) return;                    // the saved session has not been read yet
    if (!authed) {
      navigate({ to: "/" });
      return;
    }
    void refreshCategories();
  }, [ready, authed, refreshCategories, navigate]);

  // Nothing is known about the reader until the session is read: showing a
  // signed-out page for one frame would flicker on every load.
  if (!ready) return <div className="min-h-screen bg-background" />;

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex min-h-screen w-full bg-background">
        <aside
          className={cn(
            "sticky top-0 hidden h-screen shrink-0 flex-col border-e bg-sidebar p-4 transition-[width] duration-200 lg:flex",
            collapsed ? "w-[76px] items-center" : "w-[268px]",
          )}
        >
          <div className={cn("mb-8 flex items-center", collapsed ? "justify-center" : "justify-between px-1")}>
            <Link to="/dashboard" aria-label={t("shell.home")}><Wordmark compact={collapsed} /></Link>
            {!collapsed && (
              <Button variant="ghost" size="icon" aria-label={t("shell.collapse")}
                className="size-8 rounded-lg text-muted-foreground" onClick={() => setCollapsed(true)}>
                <PanelLeftClose className="size-4" />
              </Button>
            )}
          </div>

          {collapsed && (
            <Button variant="ghost" size="icon" aria-label={t("shell.expand")}
              className="mb-4 size-9 rounded-lg text-muted-foreground" onClick={() => setCollapsed(false)}>
              <PanelLeftOpen className="size-4" />
            </Button>
          )}

          <NavList collapsed={collapsed} />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur-xl">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-4 sm:px-6 lg:px-8">
              <div className="flex min-w-0 items-center gap-3">
                <Sheet open={open} onOpenChange={setOpen}>
                  <SheetTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label={t("shell.openNav")}
                      className="min-h-11 min-w-11 rounded-xl lg:hidden">
                      <Menu className="size-5" />
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="left" className="w-72 bg-sidebar p-4">
                    <SheetTitle className="sr-only">{t("shell.nav")}</SheetTitle>
                    <Link to="/dashboard" className="mb-8 block" onClick={() => setOpen(false)}><Wordmark /></Link>
                    <NavList onNavigate={() => setOpen(false)} />
                  </SheetContent>
                </Sheet>
                {title && (
                  <div className="min-w-0">
                    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Link to="/browse" className="transition-colors hover:text-foreground">{t("browse.title")}</Link>
                      <span aria-hidden>/</span>
                      <span className="truncate text-foreground/70">{title}</span>
                    </nav>
                    <h1 className="mt-0.5 truncate text-h2 font-semibold sm:text-h1">{title}</h1>
                    {description && <p className="truncate text-sm text-muted-foreground">{description}</p>}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                {action}
                <div className="mx-1 hidden h-6 w-px bg-border sm:block" />
                <LanguageToggle />
                <ThemeToggle />
                <AvatarMenu />
              </div>
            </div>
          </header>
          <main className="flex-1 px-4 py-8 sm:px-6 lg:px-8">
            <div className="mx-auto max-w-6xl animate-fade-in">{children}</div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
