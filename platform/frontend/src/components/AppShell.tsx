import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
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
import { cn } from "@/lib/utils";

export { Wordmark, BrandMark };

function useNav() {
  const { isAdmin } = useStore();
  const items = [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/results", label: "Decisions", icon: ScrollText },
  ];
  if (isAdmin) items.push({ to: "/admin", label: "Admin console", icon: ShieldCheck });
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
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={toggleTheme}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="min-h-11 min-w-11 rounded-xl">
          {theme === "dark" ? <Sun className="size-4.5" /> : <Moon className="size-4.5" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{theme === "dark" ? "Light mode" : "Dark mode"}</TooltipContent>
    </Tooltip>
  );
}

function AvatarMenu() {
  const navigate = useNavigate();
  const { email, role, logout } = useStore();
  const initials = (email || "?").slice(0, 2).toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label="Account menu"
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
          <Link to="/settings"><User className="size-4" />Profile</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            logout();
            toast.success("Signed out");
            navigate({ to: "/" });
          }}
        >
          <LogOut className="size-4" />
          Sign out
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
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const { authed, refreshCategories } = useStore();

  useEffect(() => {
    if (!authed) {
      navigate({ to: "/" });
      return;
    }
    void refreshCategories();
  }, [authed, refreshCategories, navigate]);

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
            <Link to="/dashboard" aria-label="Home"><Wordmark compact={collapsed} /></Link>
            {!collapsed && (
              <Button variant="ghost" size="icon" aria-label="Collapse sidebar"
                className="size-8 rounded-lg text-muted-foreground" onClick={() => setCollapsed(true)}>
                <PanelLeftClose className="size-4" />
              </Button>
            )}
          </div>

          {collapsed && (
            <Button variant="ghost" size="icon" aria-label="Expand sidebar"
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
                    <Button variant="ghost" size="icon" aria-label="Open navigation"
                      className="min-h-11 min-w-11 rounded-xl lg:hidden">
                      <Menu className="size-5" />
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="left" className="w-72 bg-sidebar p-4">
                    <SheetTitle className="sr-only">Navigation</SheetTitle>
                    <Link to="/dashboard" className="mb-8 block" onClick={() => setOpen(false)}><Wordmark /></Link>
                    <NavList onNavigate={() => setOpen(false)} />
                  </SheetContent>
                </Sheet>
                <div className="min-w-0">
                  <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Link to="/dashboard" className="transition-colors hover:text-foreground">القرارات</Link>
                    <span aria-hidden>/</span>
                    <span className="truncate text-foreground/70">{title}</span>
                  </nav>
                  <h1 className="mt-0.5 truncate text-h2 font-semibold sm:text-h1">{title}</h1>
                  {description && <p className="truncate text-sm text-muted-foreground">{description}</p>}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                {action}
                <div className="mx-1 hidden h-6 w-px bg-border sm:block" />
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
