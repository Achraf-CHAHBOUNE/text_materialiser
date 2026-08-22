import { ArrowLeft, Check, FileX2, Gavel, Scale, Landmark } from "lucide-react";
import { cn } from "@/lib/utils";
import { LEVEL_ORDER, type Level, type StepNode } from "@/lib/mock-data";

const ICONS: Record<Level, typeof Scale> = {
  ابتدائي: Landmark,
  استئناف: Scale,
  نقض: Gavel,
};

const FULL_NAME: Record<Level, string> = {
  ابتدائي: "المحكمة الابتدائية",
  استئناف: "محكمة الاستئناف",
  نقض: "محكمة النقض",
};

/**
 * Court-level stepper. Visual flow is RTL: ابتدائي on the right,
 * نقض on the left, connected by an animated line.
 */
export function CourtStepper({ steps }: { steps: StepNode[] }) {
  const ordered = LEVEL_ORDER.map((l) => steps.find((s) => s.level === l)).filter(
    Boolean,
  ) as StepNode[];

  const lastDoneIndex = ordered.reduce(
    (acc, s, i) => (s.status === "done" ? i : acc),
    -1,
  );

  return (
    <div dir="rtl" className="w-full">
      <ol className="relative grid gap-4 md:grid-cols-3 md:gap-0">
        {ordered.map((step, i) => {
          const Icon = ICONS[step.level];
          const done = step.status === "done";
          const current = i === lastDoneIndex;
          const isLast = i === ordered.length - 1;
          return (
            <li
              key={step.level}
              className="animate-stepper-in group relative md:px-3"
              style={{ animationDelay: `${i * 140}ms` }}
            >
              {/* connector */}
              {!isLast && (
                <span
                  aria-hidden
                  className="pointer-events-none absolute top-[46px] left-0 hidden h-0.5 w-6 -translate-x-full items-center md:flex"
                >
                  <span
                    className={cn(
                      "animate-line-grow block h-full w-full rounded-full",
                      done ? "bg-teal" : "bg-border",
                    )}
                    style={{ animationDelay: `${i * 140 + 200}ms` }}
                  />
                  <ArrowLeft
                    className={cn(
                      "absolute -left-0.5 size-3.5",
                      done ? "text-teal" : "text-border",
                    )}
                  />
                </span>
              )}
              <div
                className={cn(
                  "flex h-full flex-col gap-4 rounded-2xl border p-5 transition-all duration-200",
                  done
                    ? "border-border bg-card shadow-sm hover:-translate-y-0.5 hover:shadow-lg"
                    : "border-dashed border-border bg-muted/40 opacity-90",
                  current && "ring-2 ring-teal/40 ring-offset-2 ring-offset-background",
                )}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "grid size-11 shrink-0 place-items-center rounded-xl transition-transform duration-200 group-hover:scale-105",
                      done
                        ? "grad-brand text-primary-foreground shadow-sm"
                        : "bg-muted text-muted-foreground ring-1 ring-border",
                      current && "animate-pulse-ring",
                    )}
                  >
                    {done ? <Check className="size-5" /> : <FileX2 className="size-5" />}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <Icon className="size-3.5 shrink-0 text-teal" aria-hidden />
                      <span className="font-ar truncate text-sm font-semibold leading-6">
                        {FULL_NAME[step.level]}
                      </span>
                    </div>
                    <p className="font-ar truncate text-xs leading-6 text-muted-foreground">
                      {step.court}
                    </p>
                  </div>
                </div>

                {done ? (
                  <dl className="font-ar space-y-1.5 text-xs">
                    <Row label="القرار" value={step.decisionNumber} strong />
                    <Row label="الملف" value={step.fileNumber} strong />
                    <Row label="التاريخ" value={step.date} />
                    <Row label="المنطوق" value={step.outcome} />
                  </dl>
                ) : (
                  <div className="font-ar space-y-2 text-xs">
                    <span className="inline-flex rounded-full bg-warning/15 px-2.5 py-0.5 font-medium leading-6 text-warning-foreground ring-1 ring-warning/40 dark:text-warning">
                      غير متوفر
                    </span>
                    <p className="text-muted-foreground opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                      مشار إليه: {step.decisionNumber} — ملف {step.fileNumber} — {step.date}
                    </p>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className={cn("truncate text-end tabular-nums", strong && "font-semibold")}>{value}</dd>
    </div>
  );
}
