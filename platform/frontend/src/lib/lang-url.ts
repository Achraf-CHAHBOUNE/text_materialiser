/**
 * The language lives in the address: /ar/browse/… and /fr/browse/…
 *
 * A shared link then opens in the language it was sent in, and the server renders
 * the right one straight away instead of correcting it after the page loads. The
 * routes themselves know nothing about it: the router strips the prefix on the way
 * in and puts the current one back on the way out, so every <Link to="/browse/…">
 * keeps working unchanged.
 */
import type { LocationRewrite } from "@tanstack/react-router";

export type Lang = "ar" | "fr";
export const LANGS: Lang[] = ["ar", "fr"];
export const STORAGE_KEY = "anon-lang";

const PREFIX = /^\/(ar|fr)(?=\/|$)/;

// The language links are written in. Set from the address each time the router reads
// one, and by the language switch.
let active: Lang = "ar";

export const getActiveLang = (): Lang => active;
export const setActiveLang = (l: Lang) => {
  active = l;
};

export function langFromPath(path: string): Lang | null {
  const m = PREFIX.exec(path);
  return m ? (m[1] as Lang) : null;
}

function savedLang(): Lang | null {
  try {
    const v = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    return v === "ar" || v === "fr" ? v : null;
  } catch {
    return null;
  }
}

/** The same address in another language. */
export function swapLang(publicHref: string, to: Lang): string {
  const url = new URL(publicHref, "http://x");
  const rest = url.pathname.replace(PREFIX, "");
  return `/${to}${rest === "/" ? "" : rest}${url.search}${url.hash}`;
}

export const langRewrite: LocationRewrite = {
  input: ({ url }) => {
    const l = langFromPath(url.pathname);
    if (l) {
      active = l;
      url.pathname = url.pathname.replace(PREFIX, "") || "/";
    } else {
      // an old link with no language: the reader's last choice, else Arabic. Never
      // the previous value: on the server that is another reader's request.
      active = savedLang() ?? "ar";
    }
    return url;
  },
  output: ({ url }) => {
    if (!langFromPath(url.pathname)) {
      url.pathname = `/${active}${url.pathname === "/" ? "" : url.pathname}`;
    }
    return url;
  },
};
