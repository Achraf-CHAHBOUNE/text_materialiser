import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { FileText, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Card, day, Empty } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  deleteFolder,
  folderDetail,
  removeItem,
  setItemNote,
  type FolderDetail,
} from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/library/$folderId")({
  component: FolderPage,
});

function FolderPage() {
  const { folderId } = Route.useParams();
  const id = Number(folderId);
  const { t, lang, num } = useI18n();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const f = useQuery({ queryKey: ["folder", id, lang], queryFn: () => folderDetail(id, lang) });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["folder", id] });
  const drop = useMutation({
    mutationFn: () => deleteFolder(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["folders"] });
      navigate({ to: "/library" });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  const d = f.data;
  return (
    <AppShell
      title={d?.name ?? t("lib.title")}
      description={
        d
          ? `${num(d.items.length)} ${t("browse.rulingsCount")}${d.shared ? ` · ${t("lib.shared")}` : ""}`
          : ""
      }
      action={
        d?.mine && (
          <Button
            variant="outline"
            size="sm"
            className="text-destructive"
            onClick={() => {
              if (window.confirm(t("lib.confirmDelete"))) drop.mutate();
            }}
          >
            <Trash2 className="size-4" />
            {t("lib.delete")}
          </Button>
        )
      }
    >
      {d && d.items.length === 0 && <Empty>{t("lib.folderEmpty")}</Empty>}
      <div className="space-y-3">
        {(d?.items ?? []).map((it) => (
          <Item key={it.id} folderId={id} item={it} onChange={refresh} />
        ))}
      </div>
    </AppShell>
  );
}

function Item({
  folderId,
  item,
  onChange,
}: {
  folderId: number;
  item: FolderDetail["items"][number];
  onChange: () => void;
}) {
  const { t, lang, num, chamber } = useI18n();
  const [note, setNote] = useState(item.note);
  const save = useMutation({
    mutationFn: () => setItemNote(folderId, item.id, note),
    onSuccess: () => toast.success(t("adm.saved")),
    onError: () => toast.error(t("adm.failed")),
  });
  const remove = useMutation({
    mutationFn: () => removeItem(folderId, item.id),
    onSuccess: onChange,
  });
  const summary = lang === "fr" ? item.abstract_fr || item.abstract : item.abstract;
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link
          to="/ruling/$docId"
          params={{ docId: item.doc_id }}
          className="flex items-center gap-2 font-medium hover:text-teal"
        >
          <FileText className="size-4" />
          {t("ruling.decisionOf")} {num(item.decision_no)} · {item.date} · {chamber(item.chamber)}
        </Link>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => remove.mutate()}
          aria-label={t("lib.remove")}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
      {summary && (
        <p
          className="mt-2 line-clamp-3 text-sm text-muted-foreground"
          dir={lang === "fr" && item.abstract_fr ? "ltr" : "rtl"}
        >
          {summary}
        </p>
      )}
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
        <Textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder={t("lib.note")}
          aria-label={t("lib.note")}
          className="flex-1"
        />
        {note !== item.note && (
          <Button size="sm" onClick={() => save.mutate()}>
            {t("adm.save")}
          </Button>
        )}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {t("lib.addedBy")} {item.added_by} · {day(item.added_at)}
      </p>
    </Card>
  );
}
