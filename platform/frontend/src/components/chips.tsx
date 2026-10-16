import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

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
  const { level: levelName, dir } = useI18n();
  const map: Record<string, string> = {
    ابتدائي: "bg-primary/10 text-primary ring-primary/20 dark:bg-[#2f6da8]/18 dark:text-[#8fc0ec] dark:ring-[#2f6da8]/35",
    استئناف: "bg-teal/12 text-teal ring-teal/25",
    نقض: "bg-warning/14 text-warning-foreground ring-warning/35 dark:text-warning",
  };
  return (
    <span
      dir={dir}
      className={cn(
        "font-ar inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium leading-6 ring-1",
        map[level] ?? "bg-muted text-muted-foreground ring-border",
        className,
      )}
    >
      {levelName(level)}
    </span>
  );
}

/** Neutral chamber badge, named in the reader's language. */
export function ChamberBadge({ chamber }: { chamber: string }) {
  const { chamber: chamberName, dir } = useI18n();
  return (
    <span
      dir={dir}
      className="font-ar inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-xs leading-6 text-muted-foreground ring-1 ring-border"
    >
      {chamberName(chamber)}
    </span>
  );
}

