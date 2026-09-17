import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { toast } from "sonner";

import { ApiError, type Decision, type EditOutcome, type History } from "@/lib/api";
import { useI18n, type StringKey } from "@/lib/i18n";

export const rulingKey = (docId: string, admin: boolean) => ["ruling", docId, admin ? "admin" : "reader"];
export const historyKey = (docId: string) => ["ruling-history", docId];

const ACTIONS = ["import", "hide", "hide_all", "edit", "restore", "title", "replace_file"];

/** "hide_all" -> the translated label; an action this build does not know shows as is. */
export function useActionLabel() {
  const { t } = useI18n();
  return (action: string) =>
    ACTIONS.includes(action) ? t(`history.action.${action}` as StringKey) : action;
}

/** The server's short summary ("3 hidden", "2 change(s)"), in the reader's language.
 * Anything else -- a new title, say -- is shown as written. */
export function useSummary() {
  const { t, num } = useI18n();
  return (summary: string) => {
    const m = /^(\d+) (hidden|change\(s\))$/.exec(summary);
    if (!m) return summary;
    return `${num(Number(m[1]))} ${t(m[2] === "hidden" ? "history.hiddenCount" : "history.changeCount")}`;
  };
}

/** What every edit does when the server answers: refresh the page from the reply
 * (no second request), and say what happened -- or why not. */
export function useEdits(docId: string) {
  const qc = useQueryClient();
  const { t, num } = useI18n();

  const applyOutcome = useCallback(
    (out: EditOutcome, action?: string) => {
      qc.setQueryData<Decision>(rulingKey(docId, true), out.decision);
      qc.setQueryData<History>(historyKey(docId), (old) => ({ ...old, ...out.history }));
      void qc.invalidateQueries({ queryKey: rulingKey(docId, false) });
      void qc.invalidateQueries({ queryKey: ["browse"] });     // listing fields, search text
      void qc.invalidateQueries({ queryKey: ["corrections"] });
      if (out.deleted !== undefined) toast.success(t("history.purged"));
      else if (!out.applied && out.draft_id) toast.message(t("edit.draftSaved"));
      else if (out.applied && action?.startsWith("hide")) toast.success(`${t("edit.hidden")} ${num(out.version ?? 0)}`);
      else if (out.applied) toast.success(t("edit.saved"));
    },
    [qc, docId, t, num],
  );

  /** Details were corrected: the reply is the ruling; a new chamber may have added a
   * version (the Word file's title), so the history is fetched again. */
  const applyDecision = useCallback(
    (decision: Decision) => {
      qc.setQueryData<Decision>(rulingKey(docId, true), decision);
      void qc.invalidateQueries({ queryKey: historyKey(docId) });
      void qc.invalidateQueries({ queryKey: rulingKey(docId, false) });
      void qc.invalidateQueries({ queryKey: ["browse"] });
      toast.success(t("edit.saved"));
    },
    [qc, docId, t],
  );

  const fail = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.status === 409) {
        toast.error(t("edit.conflict"));
        void qc.invalidateQueries({ queryKey: ["ruling", docId] });
        void qc.invalidateQueries({ queryKey: historyKey(docId) });
        return;
      }
      if (e instanceof ApiError && e.message.startsWith("Personal data")) {
        toast.error(t("edit.gate"), { description: e.message.replace(/^Personal data found: /, "") });
        return;
      }
      toast.error(e instanceof Error ? e.message : String(e));
    },
    [qc, docId, t],
  );

  return { applyOutcome, applyDecision, fail };
}
