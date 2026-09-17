// The chambers of the Court of Cassation, in the order a court portal lists them,
// each with its own colour — the client's reference site gives every chamber and
// every column header a distinct colour, which is what makes a dense Arabic table
// readable at a glance. Tailwind classes are written out in full so the compiler
// keeps them.

export type ChamberStyle = {
  /** text colour for the chamber's name */
  text: string;
  /** soft background for its row / header cell */
  soft: string;
  /** solid background for a column header or active chip */
  solid: string;
  /** the ring colour when a row is focused */
  ring: string;
};

const STYLES: Record<string, ChamberStyle> = {
  "أحوال شخصية": {
    text: "text-rose-700 dark:text-rose-300",
    soft: "bg-rose-50 dark:bg-rose-950/40",
    solid: "bg-rose-600 text-white",
    ring: "ring-rose-400",
  },
  "تجارية": {
    text: "text-amber-700 dark:text-amber-300",
    soft: "bg-amber-50 dark:bg-amber-950/40",
    solid: "bg-amber-600 text-white",
    ring: "ring-amber-400",
  },
  "اجتماعية": {
    text: "text-teal-700 dark:text-teal-300",
    soft: "bg-teal-50 dark:bg-teal-950/40",
    solid: "bg-teal-600 text-white",
    ring: "ring-teal-400",
  },
  "عقارية": {
    text: "text-fuchsia-700 dark:text-fuchsia-300",
    soft: "bg-fuchsia-50 dark:bg-fuchsia-950/40",
    solid: "bg-fuchsia-600 text-white",
    ring: "ring-fuchsia-400",
  },
  "جنائية": {
    text: "text-slate-700 dark:text-slate-300",
    soft: "bg-slate-100 dark:bg-slate-900/60",
    solid: "bg-slate-700 text-white",
    ring: "ring-slate-400",
  },
  "مدنية": {
    text: "text-violet-700 dark:text-violet-300",
    soft: "bg-violet-50 dark:bg-violet-950/40",
    solid: "bg-violet-600 text-white",
    ring: "ring-violet-400",
  },
  "إدارية": {
    text: "text-sky-700 dark:text-sky-300",
    soft: "bg-sky-50 dark:bg-sky-950/40",
    solid: "bg-sky-600 text-white",
    ring: "ring-sky-400",
  },
};

const FALLBACK: ChamberStyle = {
  text: "text-muted-foreground",
  soft: "bg-muted",
  solid: "bg-muted-foreground text-background",
  ring: "ring-muted-foreground",
};

export const chamberStyle = (chamber: string): ChamberStyle => STYLES[chamber] ?? FALLBACK;

/** "أحوال شخصية" -> "غرفة الأحوال الشخصية", the way a portal names it. */
export function chamberLabel(chamber: string): string {
  const named: Record<string, string> = {
    "أحوال شخصية": "غرفة الأحوال الشخصية",
    "تجارية": "الغرفة التجارية",
    "اجتماعية": "الغرفة الاجتماعية",
    "عقارية": "الغرفة العقارية",
    "جنائية": "الغرفة الجنائية",
    "مدنية": "الغرفة المدنية",
    "إدارية": "الغرفة الإدارية",
  };
  return named[chamber] ?? chamber;
}

/** Display order: the portal's own order, then anything unexpected. */
export const CHAMBER_ORDER = [
  "أحوال شخصية", "تجارية", "اجتماعية", "عقارية", "جنائية", "مدنية", "إدارية",
];

export function byChamberOrder<T extends { chamber: string }>(a: T, b: T): number {
  const ia = CHAMBER_ORDER.indexOf(a.chamber);
  const ib = CHAMBER_ORDER.indexOf(b.chamber);
  return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
}

/** Arabic-Indic digits read more naturally in an Arabic table. */
export const arabicNumber = (n: number | string): string =>
  String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[Number(d)] ?? d);
