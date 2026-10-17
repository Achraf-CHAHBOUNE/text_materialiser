import { Link } from "@tanstack/react-router";
import { FileSearch } from "lucide-react";
import { useState } from "react";

import { when } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { findDownload, type FoundDownload } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

/** Every downloaded Word file carries a reference at the foot of its pages. Typing it
 *  here says who downloaded that copy, when, and which ruling it is. */
export function FindFile() {
  const { t, num, chamber } = useI18n();
  const [ref, setRef] = useState("");
  const [found, setFound] = useState<FoundDownload | null>(null);
  const [missing, setMissing] = useState(false);
  const look = async () => {
    setFound(null);
    setMissing(false);
    try {
      setFound(await findDownload(ref));
    } catch {
      setMissing(true);
    }
  };
  return (
    <div className="rounded-xl border bg-card p-2">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (ref.trim()) void look();
        }}
      >
        <FileSearch className="ms-1 size-4 text-muted-foreground" aria-hidden />
        <Input
          value={ref}
          onChange={(e) => setRef(e.target.value)}
          placeholder={t("trace.placeholder")}
          aria-label={t("trace.placeholder")}
          className="h-9 max-w-xs font-mono"
          dir="ltr"
        />
        <Button size="sm" variant="outline" type="submit">
          {t("trace.find")}
        </Button>
        {found && (
          <span className="text-sm">
            <Link
              to="/crm/users/$email"
              params={{ email: found.email }}
              className="font-medium text-teal hover:underline"
              dir="ltr"
            >
              {found.email}
            </Link>
            {found.org && <span className="text-muted-foreground"> · {found.org}</span>}
            <span className="text-muted-foreground"> · {when(found.at)} · </span>
            <Link to="/ruling/$docId" params={{ docId: found.doc_id }} className="hover:text-teal">
              {t("ruling.decisionOf")} {num(found.decision_no ?? "")} ·{" "}
              {chamber(found.chamber ?? "")}
            </Link>
          </span>
        )}
        {missing && <span className="text-sm text-destructive">{t("trace.none")}</span>}
      </form>
    </div>
  );
}
