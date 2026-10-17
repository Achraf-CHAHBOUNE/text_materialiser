import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { FolderOpen, FolderPlus, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Card, Empty } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { createFolder, folders } from "@/lib/api-biz";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/library/")({
  head: () => ({ meta: [{ title: "ملفاتي · Mes dossiers" }] }),
  component: Library,
});

function Library() {
  const { t, num } = useI18n();
  const { isStaff } = useStore();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["folders"], queryFn: folders });
  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);
  const create = useMutation({
    mutationFn: () => createFolder(name, shared),
    onSuccess: () => {
      setName("");
      setShared(false);
      void qc.invalidateQueries({ queryKey: ["folders"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <AppShell title={t("lib.title")} description={t("lib.subtitle")}>
      <Card>
        <form
          className="flex flex-wrap items-center gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder={t("lib.newName")}
            className="h-10 max-w-sm"
            aria-label={t("lib.newName")}
          />
          {!isStaff && (
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={shared} onCheckedChange={(v) => setShared(v === true)} />
              {t("lib.shareFirm")}
            </label>
          )}
          <Button type="submit" disabled={create.isPending}>
            <FolderPlus className="size-4" />
            {t("lib.create")}
          </Button>
        </form>
      </Card>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(list.data ?? []).map((f) => (
          <Link
            key={f.id}
            to="/library/$folderId"
            params={{ folderId: String(f.id) }}
            className="rounded-2xl border bg-card p-5 shadow-soft transition-colors hover:border-teal/50 hover:bg-teal/5"
          >
            <div className="flex items-center gap-2">
              {f.shared ? (
                <Users className="size-4 text-teal" />
              ) : (
                <FolderOpen className="size-4 text-teal" />
              )}
              <span className="font-medium">{f.name}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {num(f.count)} {t("browse.rulingsCount")}
              {f.shared ? ` · ${t("lib.shared")}` : ""}
              {!f.mine ? ` · ${f.owner}` : ""}
            </p>
          </Link>
        ))}
      </div>
      {list.data && list.data.length === 0 && (
        <div className="mt-4">
          <Empty>{t("lib.empty")}</Empty>
        </div>
      )}
    </AppShell>
  );
}
