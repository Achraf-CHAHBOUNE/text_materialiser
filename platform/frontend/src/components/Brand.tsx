import { cn } from "@/lib/utils";

/** Brand shield + "A" mark, drawn inline so it scales crisply at any size. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "grad-brand relative grid size-9 shrink-0 place-items-center rounded-xl shadow-md",
        className,
      )}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" className="size-5" fill="none">
        <path
          d="M12 2.6 4.8 5.4v6.2c0 4.6 3 8.1 7.2 9.8 4.2-1.7 7.2-5.2 7.2-9.8V5.4L12 2.6Z"
          stroke="currentColor"
          strokeWidth="1.4"
          className="text-primary-foreground/45"
        />
        <path
          d="M9.1 16.1 12 8.4l2.9 7.7M10.3 13.6h3.4"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-primary-foreground"
        />
      </svg>
    </span>
  );
}

export function Wordmark({
  className,
  compact,
}: {
  className?: string;
  compact?: boolean;
}) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <BrandMark />
      {!compact && (
        <span className="text-lg font-semibold tracking-tight">
          Anonym<span className="text-teal">ize</span>
        </span>
      )}
    </span>
  );
}
