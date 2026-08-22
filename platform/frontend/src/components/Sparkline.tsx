import { cn } from "@/lib/utils";

/** Tiny inline sparkline for stat cards. Purely decorative. */
export function Sparkline({
  data,
  className,
  tone = "teal",
}: {
  data: number[];
  className?: string;
  tone?: "teal" | "brand";
}) {
  const w = 100;
  const h = 28;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / span) * (h - 4) - 2;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const stroke = tone === "teal" ? "var(--color-teal)" : "var(--color-primary)";
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className={cn("h-7 w-full", className)}
      aria-hidden
    >
      <polyline
        points={`0,${h} ${points.join(" ")} ${w},${h}`}
        fill={stroke}
        opacity="0.1"
      />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
