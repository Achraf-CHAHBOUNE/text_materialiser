import { EyeOff, Flag, ScanSearch } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

const TOKEN = "XXXXXXX";

export type Selected = {
  value: string;
  /** which exact occurrence, counted like the server counts (null: cannot tell) */
  occurrence: number | null;
};

/** Where `node`/`offset` falls in the text of `root`, counting text nodes only. */
function offsetIn(root: Node, node: Node, offset: number): number {
  if (node.nodeType !== Node.TEXT_NODE) return -1;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let total = 0;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n === node) return total + offset;
    total += n.textContent?.length ?? 0;
  }
  return -1;
}

/** Non-overlapping occurrences before `start`, as Python's str.find loop counts them.
 * If that scan steps over `start` (overlapping text), the occurrence is ambiguous. */
function occurrenceAt(text: string, value: string, start: number): number | null {
  let seen = 0;
  for (let pos = 0; ;) {
    const at = text.indexOf(value, pos);
    if (at === start) return seen;
    if (at < 0 || at > start) return null;
    seen += 1;
    pos = at + value.length;
  }
}

/**
 * The ruling's words, with hidden text marked, and a toolbar over any selection.
 * The text is one string: marks only wrap the token, so a selection maps straight
 * back to a position in it.
 */
export function RulingText({
  text, canEdit, busy, onHide, onHideAll, onReport,
}: {
  text: string;
  canEdit: boolean;
  busy: boolean;
  onHide: (s: Selected) => void;
  onHideAll: (value: string) => void;
  onReport: (quote: string) => void;
}) {
  const { t } = useI18n();
  const root = useRef<HTMLElement>(null);
  const [sel, setSel] = useState<(Selected & { x: number; y: number }) | null>(null);

  const parts = useMemo(() => text.split(TOKEN), [text]);

  const read = useCallback(() => {
    const s = window.getSelection();
    const el = root.current;
    if (!s || s.isCollapsed || !el || s.rangeCount === 0) return setSel(null);
    const range = s.getRangeAt(0);
    if (!el.contains(range.startContainer) || !el.contains(range.endContainer)) return setSel(null);
    let start = offsetIn(el, range.startContainer, range.startOffset);
    let end = offsetIn(el, range.endContainer, range.endOffset);
    if (start < 0 || end <= start) return setSel(null);
    while (start < end && /\s/.test(text[start] ?? "")) start += 1;   // no surrounding spaces
    while (end > start && /\s/.test(text[end - 1] ?? "")) end -= 1;
    const value = text.slice(start, end);
    if (!value || !value.replaceAll(TOKEN, "").trim()) return setSel(null);
    const box = range.getBoundingClientRect();
    setSel({ value, occurrence: occurrenceAt(text, value, start), x: box.left + box.width / 2, y: box.top });
  }, [text]);

  useEffect(() => {
    const clear = () => {
      const s = window.getSelection();
      if (!s || s.isCollapsed) setSel(null);
    };
    const away = () => setSel(null);
    document.addEventListener("selectionchange", clear);
    window.addEventListener("scroll", away, true);
    return () => {
      document.removeEventListener("selectionchange", clear);
      window.removeEventListener("scroll", away, true);
    };
  }, []);

  useEffect(() => setSel(null), [text]);

  const done = () => {
    window.getSelection()?.removeAllRanges();
    setSel(null);
  };

  return (
    <>
      <article
        ref={root}
        dir="rtl"
        onMouseUp={read}
        onKeyUp={read}
        onTouchEnd={() => setTimeout(read, 0)}
        className="mt-4 whitespace-pre-wrap rounded-2xl border bg-card p-6 text-[15px] leading-8 selection:bg-amber-300/50"
      >
        {parts.map((p, i) => (
          <span key={i}>
            {p}
            {i < parts.length - 1 && (
              <mark className="rounded bg-muted px-0.5 font-mono text-[13px] text-muted-foreground">{TOKEN}</mark>
            )}
          </span>
        ))}
      </article>

      {sel && (
        <div
          role="toolbar"
          // Above the selection, but always on screen: a selection can start above the
          // visible part of the page, and a toolbar placed there could not be clicked.
          style={{
            left: Math.min(Math.max(sel.x, 140), window.innerWidth - 140),
            top: Math.min(Math.max(8, sel.y - 48), window.innerHeight - 56),
          }}
          className="fixed z-40 flex -translate-x-1/2 items-center gap-1 rounded-xl border bg-popover p-1 shadow-lg"
          onMouseDown={(e) => e.preventDefault()}          /* keep the selection */
        >
          {canEdit ? (
            <>
              <Button size="sm" disabled={busy || sel.occurrence === null}
                      onClick={() => { onHide({ value: sel.value, occurrence: sel.occurrence }); done(); }}>
                <EyeOff className="size-4" aria-hidden /> {t("edit.hide")}
              </Button>
              <Button size="sm" variant="outline" disabled={busy}
                      onClick={() => { onHideAll(sel.value); done(); }}>
                <ScanSearch className="size-4" aria-hidden /> {t("edit.hideAll")}
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" onClick={() => { onReport(sel.value); done(); }}>
              <Flag className="size-4" aria-hidden /> {t("report.title")}
            </Button>
          )}
        </div>
      )}
    </>
  );
}
