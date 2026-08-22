# Lovable — Design Enhancement Pass for "Anonymize"

Do a **comprehensive visual design polish** of the existing app. **Do not change any
functionality, routes, data, or API calls** — this is a UI/UX upgrade only. Goal: make
it look like a premium, trustworthy, "legal-grade" SaaS (think Linear / Vercel / Stripe
level of polish), with first-class Arabic RTL.

## 1) Design language (apply globally via tokens/theme)
- **Palette:** primary deep navy `#1E3A5F`, accent teal `#0E9F9A`; add a subtle brand
  gradient for hero/CTA (navy→teal). Semantic: success `#16A34A`, warning amber `#D97706`
  (use for `review=check`), danger `#DC2626`. Neutrals: a true slate ramp (50→900).
- **Elevation & depth:** consistent shadow scale (sm/md/lg), `rounded-xl` (16px) cards,
  1px hairline borders in light, translucent surfaces + soft glow in dark.
- **Spacing:** strict 8pt grid; increase whitespace/padding in cards, tables, and headers.
- **Typography scale:** Inter for UI with a clear type ramp (display / h1 / h2 / body /
  caption); tabular-nums for numbers/dates. Tighten line-heights on headings.
- **Icons:** use lucide consistently (one icon set, one weight).

## 2) Dark + light mode
- Add a proper theme toggle (respect system). In dark mode use layered surfaces
  (bg `#0B1220`, card `#111A2B`, border `#1F2A3D`), sufficient contrast (WCAG AA), and
  soften pure-white text to `#E5EAF2`. Ensure charts, chips, and the stepper look
  intentional in both themes.

## 3) Arabic / RTL polish (important)
- Load a proper Arabic font (**"IBM Plex Sans Arabic"** or **"Cairo"**) and apply it to
  all Arabic text; set `dir="rtl"` on Arabic blocks, right-align, and increase
  line-height for legibility. Mirror padding/margins and icon positions for RTL content.
  Keep the app chrome LTR but make Arabic content feel native, not bolted-on.

## 4) Global chrome
- **Sidebar:** refined, with a logo/wordmark, grouped nav with icons, active-state pill,
  collapsible, and a user/workspace switcher at the bottom. Subtle divider from content.
- **Top bar:** breadcrumb/title, theme toggle, notifications, avatar menu.
- Add a real **logo/wordmark** and a favicon (shield + "A" motif).

## 5) Per-screen upgrades
- **Login/Signup:** center card on a branded split background (gradient or subtle legal
  pattern), clearer primary vs secondary buttons, better field styling, brand lockup.
- **Dashboard:** turn KPI tiles into polished stat cards (icon, big tabular number, delta,
  tiny sparkline); a prominent "New job" CTA; recent-jobs list with colored status chips.
- **New Job (Upload):** make the dropzone large and inviting (dashed border, icon, hover
  state); uploaded files as clean removable chips with type icon + size; sticky primary CTA.
- **Processing:** a smooth animated progress bar with % and "N of M"; a live feed with
  per-row status ticks; nice completion state.
- **Results tables (Documents & Cases):** sticky headers, comfortable row height, zebra or
  hover highlight, column sorting affordances, a filter bar with chips, and **badges**:
  chamber (neutral), level (ابتدائي/استئناف/نقض color-coded), `appealed/cassated` as green
  pills, `review=check` as an amber warning badge with tooltip. Add skeleton loaders and a
  friendly empty state.
- **Case Explorer — the hero (make it stand out):** a horizontal **court-level stepper**
  المحكمة الابتدائية → محكمة الاستئناف → محكمة النقض. Node states: **done** (solid brand,
  check, shows file/decision/date/outcome), **top/current** (highlighted ring),
  **missing** (dashed, muted, label "غير متوفر"). Animated connector line between nodes;
  hover to reveal details; RTL-aware flow with clear directional arrows. Below it, member
  documents with an RTL anonymized-text preview card (names as `XXXXXXX`, monospace token).
- **Billing & Usage:** clean plan cards (Free/Pro/Firm) with a highlighted recommended
  plan, a usage meter (radial or bar) vs quota, and a clear upgrade CTA.
- **Settings:** sectioned cards, clean forms, members table with role pills.

## 6) Micro-interactions & states
- Subtle transitions (150–200ms) on hover/press/route-change; progress + stepper animate
  on mount; toasts for actions. Add **loading skeletons**, **empty states** (illustration +
  guidance), **error states**, and a branded **404**.

## 7) Consistency & accessibility pass
- Unify corner radii, shadows, button variants, chip styles, and spacing across every page.
- Ensure visible focus rings, keyboard navigation, AA contrast, and readable hit targets.

## Priority order
1) Global tokens (palette/type/spacing/radius/shadows) + dark mode + Arabic font.
2) Sidebar/top-bar chrome + logo/favicon.
3) Tables + badges + the **Case Explorer stepper** (signature).
4) Dashboard stat cards, upload, processing.
5) Micro-interactions, skeletons, empty/error/404, billing/settings polish.

Keep it clean and restrained — lots of whitespace, few accent colors, strong hierarchy.
Do not introduce new dependencies that break the build; reuse the existing component
library (shadcn/ui) and just elevate its styling.
