// Small pieces every business page uses, so the CRM, the account and the library look
// like the rest of the site: the same cards, the same badges, the same money.
import type { ReactNode } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Lang } from "@/lib/lang-url";
import { cn } from "@/lib/utils";

/** 49900 -> "499,00 MAD" / "499,00 درهم". Amounts arrive in centimes. */
export function money(centimes: number, lang: Lang): string {
  const v = (centimes / 100).toLocaleString("fr-MA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return lang === "ar" ? `${v} درهم` : `${v} MAD`;
}

/** "2026-10-15" or an ISO timestamp -> 15/10/2026 (both languages write it so). */
export function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.slice(0, 10).split("-");
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : iso;
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return `${day(iso)} ${iso.slice(11, 16)}`;
}

export function Card({ title, action, children, className }: {
  title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={cn("rounded-2xl border bg-card p-5 shadow-soft", className)}>
      {(title || action) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, tone = "default", hint }: {
  label: string; value: ReactNode; tone?: "default" | "good" | "warn" | "bad"; hint?: ReactNode;
}) {
  const color = { default: "text-foreground", good: "text-teal", warn: "text-amber-600", bad: "text-destructive" }[tone];
  return (
    <div className="rounded-2xl border bg-card p-4 shadow-soft">
      <p className={cn("text-2xl font-semibold tabular-nums", color)}>{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

const TONES: Record<string, string> = {
  good: "bg-teal/12 text-teal ring-teal/25",
  warn: "bg-amber-500/12 text-amber-700 ring-amber-500/30 dark:text-amber-300",
  bad: "bg-destructive/10 text-destructive ring-destructive/25",
  info: "bg-sky-500/10 text-sky-700 ring-sky-500/25 dark:text-sky-300",
  muted: "bg-muted text-muted-foreground ring-border",
};

/** Which tone each status reads as, wherever it appears. */
export const STATUS_TONE: Record<string, keyof typeof TONES> = {
  ok: "good", active: "good", paid: "good", won: "good", customer: "good", converted: "good", closed: "muted",
  trial: "info", new: "info", open: "info", demo: "info", contacted: "info", qualified: "info", prospect: "info",
  sent: "muted", pending: "warn", quiet: "warn", draft: "muted",
  expired: "bad", overdue: "bad", suspended: "bad", lost: "bad", rejected: "muted", at_risk: "bad",
  cancelled: "muted", former: "muted", none: "muted", high: "bad", normal: "muted",
};

export function Badge({ tone = "muted", children }: { tone?: keyof typeof TONES | undefined; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1", TONES[tone])}>
      {children}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">{children}</p>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

export function TextField({ label, value, onChange, type = "text", placeholder, required, dir }: {
  label: string; value: string; onChange: (v: string) => void; type?: string;
  placeholder?: string; required?: boolean; dir?: "ltr" | "rtl";
}) {
  return (
    <Field label={label}>
      <Input type={type} value={value} required={required} placeholder={placeholder} dir={dir}
             onChange={(e) => onChange(e.target.value)} className="h-10" />
    </Field>
  );
}

export function Table({ head, children, minWidth = "40rem" }: { head: ReactNode[]; children: ReactNode; minWidth?: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full text-sm" style={{ minWidth }}>
        <thead>
          <tr className="border-b bg-muted/40 text-xs font-semibold text-muted-foreground">
            {head.map((h, i) => <th key={i} className="px-3 py-2.5 text-start">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y">{children}</tbody>
      </table>
    </div>
  );
}

export const Td = ({ children, className }: { children?: ReactNode; className?: string }) =>
  <td className={cn("px-3 py-2.5 align-top", className)}>{children}</td>;

export function Select({ value, onChange, options, className, label }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
  className?: string; label?: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}
            className={cn("h-10 rounded-md border border-input bg-background px-3 text-sm", className)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
