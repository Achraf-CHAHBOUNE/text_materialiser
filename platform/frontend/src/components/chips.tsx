import { CheckCircle2, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { Review } from "@/lib/mock-data";

export function ReviewBadge({ review }: { review: Review }) {
  if (review === "ok") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-success/12 px-2.5 py-1 text-xs font-medium text-success ring-1 ring-success/25">
        <CheckCircle2 className="size-3.5" aria-hidden />
        ok
      </span>
    );
  }
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            tabIndex={0}
            className="inline-flex cursor-help items-center gap-1.5 rounded-full bg-warning/15 px-2.5 py-1 text-xs font-medium text-warning-foreground ring-1 ring-warning/40 dark:text-warning"
          >
            <ShieldAlert className="size-3.5" aria-hidden />
            check
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-56">
          Low-confidence matches detected — a human should verify the redactions before export.
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function Pill({
  children,
  tone = "muted",
  className,
}: {
  children: React.ReactNode;
  tone?: "muted" | "teal" | "brand" | "success" | "warning" | "danger";
  className?: string;
}) {
  const tones = {
    muted: "bg-muted text-muted-foreground ring-1 ring-border",
    teal: "bg-teal/12 text-teal ring-1 ring-teal/25",
    brand: "bg-primary/10 text-primary ring-1 ring-primary/20 dark:bg-teal/10 dark:text-teal",
    success: "bg-success/12 text-success ring-1 ring-success/25",
    warning: "bg-warning/15 text-warning-foreground ring-1 ring-warning/35 dark:text-warning",
    danger: "bg-destructive/12 text-destructive ring-1 ring-destructive/25",
  } as const;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Court level badge — one colour per level, consistent everywhere. */
export function LevelBadge({ level, className }: { level: string; className?: string }) {
  const map: Record<string, string> = {
    ابتدائي: "bg-primary/10 text-primary ring-primary/20 dark:bg-[#2f6da8]/18 dark:text-[#8fc0ec] dark:ring-[#2f6da8]/35",
    استئناف: "bg-teal/12 text-teal ring-teal/25",
    نقض: "bg-warning/14 text-warning-foreground ring-warning/35 dark:text-warning",
  };
  return (
    <span
      dir="rtl"
      className={cn(
        "font-ar inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium leading-6 ring-1",
        map[level] ?? "bg-muted text-muted-foreground ring-border",
        className,
      )}
    >
      {level}
    </span>
  );
}

/** Neutral chamber badge for Arabic chamber names. */
export function ChamberBadge({ chamber }: { chamber: string }) {
  return (
    <span
      dir="rtl"
      className="font-ar inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-xs leading-6 text-muted-foreground ring-1 ring-border"
    >
      {chamber}
    </span>
  );
}

export function StatusChip({ status }: { status: "completed" | "processing" | "failed" }) {
  const map = {
    completed: { label: "Completed", cls: "bg-success/12 text-success ring-success/25" },
    processing: { label: "Processing", cls: "bg-teal/12 text-teal ring-teal/25" },
    failed: { label: "Failed", cls: "bg-destructive/12 text-destructive ring-destructive/25" },
  } as const;
  const s = map[status];
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2.5 py-1 text-xs font-medium ring-1",
        s.cls,
      )}
    >
      <span
        className={cn(
          "me-1.5 self-center size-1.5 rounded-full bg-current",
          status === "processing" && "animate-pulse",
        )}
      />
      {s.label}
    </span>
  );
}
