import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Download, Eye, Search } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { Card, Empty, when } from "@/components/biz";
import { history } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/history")({
  head: () => ({ meta: [{ title: "السجل · Historique" }] }),
  component: History,
});

const ICON = { view: Eye, search: Search, download: Download };

function History() {
  const { t, num, chamber } = useI18n();
  const list = useQuery({ queryKey: ["history"], queryFn: history });
  return (
    <AppShell title={t("hist.title")} description={t("hist.subtitle")}>
      <Card>
        {list.data && list.data.length === 0 && <Empty>{t("hist.empty")}</Empty>}
        <ul className="divide-y">
          {(list.data ?? []).map((h, i) => {
            const Icon = ICON[h.action];
            return (
              <li key={i} className="flex items-center gap-3 py-2.5 text-sm">
                <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="w-36 shrink-0 tabular-nums text-xs text-muted-foreground">
                  {when(h.ts)}
                </span>
                {h.action === "search" ? (
                  <Link
                    to="/browse/$chamber"
                    params={{ chamber: "الكل" }}
                    search={{ q: h.query }}
                    className="hover:text-teal"
                  >
                    {t("hist.searched")} « {h.query} »
                  </Link>
                ) : (
                  <Link
                    to="/ruling/$docId"
                    params={{ docId: h.doc_id ?? "" }}
                    className="hover:text-teal"
                  >
                    {h.action === "download" ? t("hist.downloaded") : t("hist.read")}{" "}
                    {t("ruling.decisionOf")} {num(h.decision_no ?? "")}
                    <span className="text-muted-foreground">
                      {" "}
                      · {h.date} · {chamber(h.chamber ?? "")}
                    </span>
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </Card>
    </AppShell>
  );
}
