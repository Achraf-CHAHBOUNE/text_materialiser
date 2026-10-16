import { useEffect } from "react";

import { request } from "./api";
import type { Lang } from "./lang-url";

const BEAT = 30;   // seconds between beats

/** While a ruling is open and the tab is in view, tell the server every half minute.
 *  A page left in a background tab, or closed at once, counts nothing. */
export function useReadingTime(docId: string | undefined, lang: Lang, enabled: boolean) {
  useEffect(() => {
    if (!docId || !enabled || typeof document === "undefined") return;
    let seen = 0;
    const tick = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      seen += 5;
      if (seen >= BEAT) {
        seen = 0;
        void request(`/api/decisions/${encodeURIComponent(docId)}/reading`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ seconds: BEAT, lang }),
        }).catch(() => undefined);
      }
    }, 5000);
    return () => window.clearInterval(tick);
  }, [docId, lang, enabled]);
}
