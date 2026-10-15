import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, BookmarkCheck, Download, FolderPlus, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { decisionFileUrl, getToken } from "@/lib/api";
import { addToFolder, createFolder, folders, rulingFolders } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

/** Download, through fetch rather than a plain link: past the day's quota the server
 *  answers 429, and a link would save that answer as the "file". */
export function DownloadButton({ docId, fileName }: { docId: string; fileName: string }) {
  const { t, num } = useI18n();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const r = await fetch(decisionFileUrl(docId), { headers: { Authorization: `Bearer ${getToken()}` } });
      if (r.status === 429) {
        const d = (await r.json().catch(() => ({}))).detail ?? {};
        toast.error(d.quota !== undefined ? `${t("dl.quota")} (${num(d.quota)})` : t("dl.pace"));
        return;
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = fileName || `${docId}.docx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("adm.failed"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button size="sm" onClick={run} disabled={busy}>
      {busy ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" aria-hidden />} {t("ruling.download")}
    </Button>
  );
}

/** File the ruling in one of my folders, or in a new one. */
export function SaveToFolder({ docId }: { docId: string }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const list = useQuery({ queryKey: ["folders"], queryFn: folders, enabled: open });
  const inside = useQuery({ queryKey: ["ruling-folders", docId], queryFn: () => rulingFolders(docId) });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["ruling-folders", docId] });
    void qc.invalidateQueries({ queryKey: ["folders"] });
  };
  const add = useMutation({
    mutationFn: (folderId: number) => addToFolder(folderId, docId),
    onSuccess: () => { toast.success(t("lib.saved")); refresh(); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  const create = useMutation({
    mutationFn: async () => {
      const f = await createFolder(name, false);
      await addToFolder(f.id, docId);
    },
    onSuccess: () => { setName(""); toast.success(t("lib.saved")); refresh(); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  const saved = (inside.data ?? []).length > 0;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">
          {saved ? <BookmarkCheck className="size-4 text-teal" /> : <Bookmark className="size-4" />}
          {saved ? t("lib.inFolder") : t("lib.save")}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-3">
        <p className="mb-2 text-xs font-medium text-muted-foreground">{t("lib.chooseFolder")}</p>
        <ul className="max-h-56 space-y-1 overflow-auto">
          {(list.data ?? []).map((f) => {
            const has = (inside.data ?? []).includes(f.id);
            return (
              <li key={f.id}>
                <button type="button" disabled={has || add.isPending} onClick={() => add.mutate(f.id)}
                        className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-start text-sm hover:bg-accent disabled:opacity-60">
                  <span>{f.name}</span>{has && <BookmarkCheck className="size-4 text-teal" />}
                </button>
              </li>
            );
          })}
        </ul>
        <form className="mt-2 flex gap-1 border-t pt-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder={t("lib.newName")}
                 className="h-8 text-sm" aria-label={t("lib.newName")} />
          <Button size="sm" type="submit" disabled={create.isPending} aria-label={t("lib.create")}><FolderPlus className="size-4" /></Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}
