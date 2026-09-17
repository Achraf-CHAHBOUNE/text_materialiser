import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { correctDecision, type Decision } from "@/lib/api";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

import { useEdits } from "./useEdits";

type Fields = { decision_no: string; decision_date: string; city: string; file_no: string; category: string };

const DATE = /^\d{2}\/\d{2}\/\d{4}$/;

/** The listing fields, edited in place. A new chamber also retitles the Word file. */
export function DetailsForm({ d, onDone }: { d: Decision; onDone: () => void }) {
  const { t, chamber } = useI18n();
  const { categories } = useStore();
  const { applyDecision, fail } = useEdits(d.doc_id);
  const initial: Fields = {
    decision_no: d.decision_no, decision_date: d.date, city: d.city ?? "",
    file_no: d.file_no, category: d.category,
  };
  const [f, setF] = useState<Fields>(initial);
  const set = (k: keyof Fields) => (v: string) => setF((o) => ({ ...o, [k]: v }));

  const changes = Object.fromEntries(
    (Object.keys(f) as (keyof Fields)[]).filter((k) => f[k].trim() !== initial[k]).map((k) => [k, f[k].trim()]),
  );
  const dateOk = !f.decision_date.trim() || DATE.test(f.decision_date.trim());

  const save = useMutation({
    mutationFn: () => correctDecision(d.doc_id, changes),
    onSuccess: (decision) => {
      applyDecision(decision);
      onDone();
    },
    onError: fail,
  });

  const field = (label: string, k: keyof Fields, extra: { placeholder?: string; invalid?: boolean } = {}) => (
    <label className="rounded-xl border bg-card px-3 py-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Input
        value={f[k]}
        onChange={(e) => set(k)(e.target.value)}
        placeholder={extra.placeholder ?? ""}
        aria-invalid={extra.invalid || undefined}
        className={`mt-1 h-8 tabular-nums ${extra.invalid ? "border-destructive" : ""}`}
      />
    </label>
  );

  return (
    <div className="mt-4 space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {field(t("col.number"), "decision_no")}
        {field(t("col.date"), "decision_date", { placeholder: "DD/MM/YYYY", invalid: !dateOk })}
        {field(t("col.city"), "city")}
        {field(t("col.fileNo"), "file_no")}
        <label className="rounded-xl border bg-card px-3 py-2">
          <span className="text-xs text-muted-foreground">{t("col.chamber")}</span>
          <Select value={f.category} onValueChange={set("category")}>
            <SelectTrigger className="mt-1 h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[...new Set([...categories, d.category])].map((c) => (
                <SelectItem key={c} value={c}>{chamber(c)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
      </div>
      <div className="flex gap-2">
        <Button size="sm" disabled={!Object.keys(changes).length || !dateOk || save.isPending}
                onClick={() => save.mutate()}>
          {t("edit.save")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>{t("edit.cancel")}</Button>
      </div>
    </div>
  );
}
