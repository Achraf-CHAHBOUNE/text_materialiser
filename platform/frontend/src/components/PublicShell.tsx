import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Wordmark } from "@/components/Brand";
import { useI18n } from "@/lib/i18n";

/** The frame of the pages a visitor sees without an account. */
export function PublicShell({ children }: { children: ReactNode }) {
  const { t, dir, lang, setLang } = useI18n();
  return (
    <div dir={dir} className="min-h-screen bg-background">
      <header className="border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <Link to="/pricing" aria-label={t("shell.home")}><Wordmark /></Link>
          <nav className="flex items-center gap-2 text-sm">
            <Link to="/pricing" className="rounded-lg px-3 py-2 hover:bg-accent">{t("pub.plans")}</Link>
            <Link to="/" className="rounded-lg px-3 py-2 hover:bg-accent">{t("login.submit")}</Link>
            <button type="button" onClick={() => setLang(lang === "ar" ? "fr" : "ar")}
                    className="rounded-lg border px-3 py-1.5 font-medium hover:bg-accent">
              {lang === "ar" ? "Français" : "العربية"}
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-10">{children}</main>
      <footer className="border-t py-6 text-center text-xs text-muted-foreground">{t("pub.footer")}</footer>
    </div>
  );
}
