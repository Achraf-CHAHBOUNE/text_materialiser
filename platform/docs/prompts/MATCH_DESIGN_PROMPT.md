# Lovable — Match this exact design system ("Anonymize")

Re-skin the existing app to **exactly match** the design below (extracted from an approved
mockup). **Keep all functionality/routes/API calls unchanged** — this is styling only.
Implement the tokens as CSS variables (and map them into the Tailwind/shadcn theme), then
restyle every component to use them.

## Fonts (add to index.html head)
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
```
- UI: **Inter**. Arabic content: **IBM Plex Sans Arabic** (`dir="rtl"`, line-height 1.9).
- Numbers/dates/tokens: **IBM Plex Mono** with `font-variant-numeric: tabular-nums`.

## Design tokens (paste verbatim; light = default, dark = `body[data-theme="dark"]`)
```css
:root{
--s50:#f8fafc;--s100:#f1f5f9;--s200:#e6ebf2;--s300:#cbd5e1;--s400:#94a3b8;--s500:#64748b;--s600:#475569;--s700:#334155;--s800:#1e293b;--s900:#0f172a;
--bg:#f4f7fb;--panel:#ffffff;--panel2:#f8fafc;--sunken:#f1f5f9;--ink:#0f172a;--ink2:#475569;--muted:#7387a0;
--line:#e6ebf2;--lineStrong:#d8e0ea;--chip:#f1f5f9;
--brand:#1E3A5F;--brandInk:#ffffff;--brandSoft:#e9eff7;--brandLine:#c9d8ea;
--teal:#0E9F9A;--tealSoft:#e2f5f4;--tealLine:#b7e5e2;
--ok:#16A34A;--okSoft:#e7f7ed;--warn:#D97706;--warnSoft:#fdf1de;--danger:#DC2626;--dangerSoft:#fdeaea;
--grad:linear-gradient(135deg,#1E3A5F 0%,#17565f 55%,#0E9F9A 100%);
--sh-sm:0 1px 2px rgba(15,23,42,.06);
--sh-md:0 1px 2px rgba(15,23,42,.05),0 8px 20px -12px rgba(15,23,42,.22);
--sh-lg:0 2px 4px rgba(15,23,42,.06),0 28px 56px -24px rgba(15,23,42,.34);
--ring:0 0 0 4px rgba(14,159,154,.16);
}
body[data-theme="dark"]{
--s50:#0f172a;--s100:#16203a;--s200:#1F2A3D;--s300:#2c3a52;--s400:#5d7191;--s500:#8b9cb3;--s600:#c3cddc;--s700:#dbe3ee;--s800:#eef2f8;--s900:#ffffff;
--bg:#0B1220;--panel:#111A2B;--panel2:#141F33;--sunken:#0e1726;--ink:#E5EAF2;--ink2:#c3cddc;--muted:#8b9cb3;
--line:#1F2A3D;--lineStrong:#2a3850;--chip:#18243a;
--brand:#5b93d6;--brandInk:#07121f;--brandSoft:#152640;--brandLine:#24405f;
--teal:#2CC3BD;--tealSoft:#0e2c2d;--tealLine:#1d5150;
--ok:#4ade80;--okSoft:#0f2a1b;--warn:#fbbf24;--warnSoft:#2c2110;--danger:#fb7185;--dangerSoft:#2f1420;
--grad:linear-gradient(135deg,#16294a 0%,#12464c 55%,#0E9F9A 100%);
--sh-sm:0 1px 2px rgba(0,0,0,.5);
--sh-md:0 1px 2px rgba(0,0,0,.5),0 10px 26px -14px rgba(0,0,0,.9);
--sh-lg:0 2px 6px rgba(0,0,0,.5),0 30px 60px -26px rgba(0,0,0,1);
--ring:0 0 0 4px rgba(44,195,189,.18);
}
```
Theme toggle sets `document.body.dataset.theme = 'light'|'dark'` (default = system).

## Global rules
```css
body{background:var(--bg);color:var(--ink);font-family:Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
:focus-visible{outline:2px solid var(--teal);outline-offset:2px;border-radius:8px}
a{color:var(--teal)} a:hover{color:var(--brand)}
.ar{font-family:"IBM Plex Sans Arabic",Inter,sans-serif;line-height:1.9}
.num{font-variant-numeric:tabular-nums}
.lift{transition:transform .18s,box-shadow .18s,border-color .18s} .lift:hover{transform:translateY(-2px);box-shadow:var(--sh-lg)}
.row-h:hover{background:var(--panel2)}
/* keyframes: fadeUp, fadeIn, popIn, lineGrow(scaleX 0→1), shimmer, toastIn, pulseRing */
```

## Component conventions (match exactly)
- **Radii:** inputs & buttons `12px`; cards `16px` (rounded-xl); small buttons `10px`; pills/chips `999px`; code tag `6px`.
- **Inputs:** height `44px`, `1px solid var(--line)`, `var(--panel)` bg, `--sh-sm`.
- **Primary button:** height `46px`, `background:var(--grad)`, white text, `--sh-md`, hover `brightness(1.08) + translateY(-1px)`.
- **Secondary button:** `var(--panel)` bg, `1px solid var(--line)`, hover `var(--panel2)`.
- **Cards/panels:** `var(--panel)` bg, `1px solid var(--line)`, radius 16, `--sh-md`; use `.lift` on clickable cards.
- **Surfaces:** page `--bg`, cards `--panel`, insets/tracks `--sunken`, chips `--chip`.
- **Pill helper:** `display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid <bd>`.
- **Level pills** (Arabic, use `.ar`): ابتدائي = `chip/ink2/line`; استئناف = `brandSoft/brand/brandLine`; نقض = `tealSoft/teal/tealLine`.
- **PII pill** (mono): count `>5` → `dangerSoft/danger`; `>0` → `warnSoft/warn`; `0` → `chip/muted`.
- **Review badge:** `review=check` → `warnSoft/warn` with an alert icon + tooltip; `ok` → subtle.
- Icons: lucide, stroke ~1.7.

## Screens & layout (match the mockup)
- **Login:** two columns — left = `--grad` panel with logo, headline "Redact once. Follow the case everywhere.", RTL level chips (ابتدائي/استئناف/نقض), footer "Processed in-region · ISO 27001 · Loi 09-08"; right = centered sign-in card (email, password + "Forgot?", gradient "Sign in", divider, "Continue with Google", "Create one").
- **App shell:** left **sidebar** (logo + wordmark, grouped nav with icons + active pill, collapsible, workspace switcher at bottom); top bar with title, quota pill, theme toggle, avatar.
- **Dashboard:** stat cards (icon, big `.num`, delta, thin progress bar in `--sunken`), "New job" CTA, recent-jobs list with status chips.
- **New job:** large dashed dropzone; uploaded files as removable chips (type icon + size, hover-danger remove); replacement-token shown in a mono code tag; primary "Start" CTA.
- **Processing:** tall progress bar (`--sunken` track, `--grad` fill, 10px, radius 999) with %, live feed of rows.
- **Results:** tabs **Documents** / **Cases**. Tables: sticky header, `.row-h` hover, level pills, PII pills, review badge, filter input + level filter, sortable. Cases show trajectory + appealed/cassated + missing + review.
- **Case Explorer (signature):** horizontal **court-level stepper** ابتدائي → استئناف → نقض. Node card per level (court, file no., decision no., date, outcome). States: **done** = solid brand + check badge; **current** = ring/`pulseRing`; **missing** = dashed `--lineStrong`, muted, label "غير متوفر". Animated connector via `lineGrow` (`scaleX`). Below: member docs; clicking one shows an RTL anonymized-text preview (names as `XXXXXXX` in mono).
- **Billing:** three plan cards (Free/Pro/Firm), recommended one highlighted with brand border; usage meter vs quota.
- **Settings:** sectioned cards; members table with initials avatars + role pills; retention toggle.
- **Empty / error / 404:** centered, `fadeUp`, icon + guidance.

## Acceptance
The re-skinned app matches these tokens, radii, shadows, fonts, pills, and the stepper
states, in **both light and dark**, with correct **RTL** for all Arabic. No functionality
changes. Reuse shadcn/ui; add no build-breaking dependencies.
