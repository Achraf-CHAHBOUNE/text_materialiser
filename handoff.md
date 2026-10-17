# Project audit and improvement handoff

Date: 2026-10-17

## Scope

Reviewed the full repository structure and concentrated implementation work on the user-facing React/TanStack frontend and its API-facing states. Backend and anonymization pipeline behavior were left intact and verified with their complete test suites.

## Changes made

### Theme and visual consistency

- Fixed dark mode. The UI previously wrote `data-theme="dark"`, while the Tailwind theme uses the `.dark` selector, so the dark palette never activated.
- The app now toggles the correct root class, sets the browser `color-scheme`, persists the choice, and uses the operating-system preference when no choice has been saved.
- Replaced the empty screen shown while the saved session loads with an accessible loading indicator.

### Navigation and RTL UX

- Made the brand/home link role-aware:
  - admin/editor -> dashboard
  - sales -> CRM
  - clients -> jurisprudence browser
- Fixed the mobile drawer so it opens from the right in Arabic and from the left in French.
- Authenticated users who revisit the sign-in page are now redirected to the correct workspace instead of seeing a login form they no longer need.

### Decisions search UX and performance

- Replaced manual request state with TanStack Query caching.
- Added a 300 ms input debounce, avoiding an API request on every keystroke.
- Removed the stale-response race where a slower old request could replace newer results.
- Kept prior results visible during filter changes to reduce layout flicker.
- Added loading indicators, skeleton rows, result counts, clear-filter controls, a real error state, and retry.
- Fixed search snippets appearing detached at the bottom of the table; each snippet now stays directly under its decision.
- Improved keyboard behavior for clickable rows (`Enter` and `Space`, with scroll prevention).
- Added Arabic and French labels for all new states.

### Dependency security

- Updated the TanStack Start dependency chain from the vulnerable `1.168.x` installation to `1.169.3` and refreshed compatible transitive packages.
- This removes the unauthenticated reflected-XSS advisory reported against the prior TanStack Start/server packages.
- Applied compatible transitive patches for `js-yaml`, `nanoid`, and `source-map-js`.
- `npm audit --omit=dev` now reports **0 vulnerabilities** (previously 5 critical and 4 high).

## Files changed

- `platform/frontend/package.json`
- `platform/frontend/package-lock.json`
- `platform/frontend/src/components/AppShell.tsx`
- `platform/frontend/src/lib/app-store.tsx`
- `platform/frontend/src/lib/i18n.tsx`
- `platform/frontend/src/routes/index.tsx`
- `platform/frontend/src/routes/results.tsx`
- `platform/frontend/src/routes/__root.tsx`
- `handoff.md`

## Verification

- Frontend production build: passed (`npm run build`)
- Frontend TypeScript check: passed (`npx tsc --noEmit`)
- Frontend dependency audit: passed, 0 vulnerabilities
- Backend: **165 passed**
- Anonymization pipeline: **159 passed**
- `git diff --check`: passed
- Targeted lint on changed frontend files: no new correctness issues; one pre-existing Fast Refresh warning remains in `app-store.tsx` because the module exports both a provider and a hook.

Browser automation was not available in this session, so responsive and visual behavior was verified by source review and production build rather than screenshot-based QA.

## Important remaining risks and recommended next work

### 1. Authentication token exposure (high priority)

API bearer tokens are stored in `localStorage`, and download URLs append the token as a query parameter. Query tokens can leak through server/proxy logs, copied URLs, browser history, analytics, or referrer headers. Prefer secure, `HttpOnly`, `SameSite` cookies for the session and short-lived, single-use signed download URLs (or authenticated fetch + Blob download).

Relevant code: `platform/frontend/src/lib/api.ts` (`TOKEN_KEY`, `tokenQ`, `decisionFileUrl`, `adminFileUrl`, and other file URL helpers).

### 2. Global lint signal is buried

The repository-wide frontend lint command currently reports roughly 11,000 issues, overwhelmingly Prettier and CRLF/LF differences. This makes real lint failures difficult to notice. Establish one line-ending policy in `.gitattributes`, run formatting once in a dedicated commit, and then enforce it in CI. Keep that separate from feature commits to preserve useful review history.

### 3. Python 3.13 deprecations

The tests pass, but they emit many warnings, mainly from naive UTC APIs (`datetime.utcnow()` / `utcfromtimestamp()`), FastAPI `on_event`, Alembic's legacy path separator, and `openpyxl`. Migrate application timestamps to timezone-aware UTC values before these APIs are removed. Start with `platform/backend/logs.py`, `accounts.py`, `limits.py`, `db.py`, and `pipeline/anonymizer/llm/vertex.py`.

### 4. Frontend bundle weight

The largest raw client assets after build are approximately 295 KB for the main entry, 128 KB for the full bilingual string catalog, 112 KB for `AppShell`, and 108 KB for CSS. Useful follow-up work:

- split the translation catalog by language and feature area;
- lazy-load CRM/admin navigation dependencies for client accounts;
- inspect the entry bundle with a bundle visualizer before changing dependencies;
- self-host/subset the two font families if first-load performance is important on slower Moroccan mobile connections.

### 5. Decisions list scalability

The decisions screen still caps the unsearched list at 100 records and has no pagination. Add server-backed pagination (or a virtualized infinite list) before exposing this screen to large administrative workflows. Preserve the new query key structure so each page/filter combination remains cacheable.

### 6. SSR language and theme polish

The root HTML shell initially declares Arabic/RTL and the client corrects it after hydration for French routes. Likewise, system theme selection is finalized after mount. Moving language and theme detection into the server request/bootstrap path would eliminate the last possible direction/theme flash.

## Suggested Claude Code prompt

> Read `handoff.md` and continue from the current working tree. Preserve the implemented UI/UX fixes. First address authentication token leakage by designing a backward-compatible HttpOnly-cookie session and safe authenticated download flow, with backend tests. Then isolate repository-wide formatting in its own commit and make lint useful in CI. Do not mix mass formatting with functional changes.

---

# Response

Date: 2026-10-17 · Branch `build/pipeline-and-platform` · 10 commits, `7a6f8c2` → `e3f161a`, all pushed.

**Result:** all six risks are dealt with (five fixed, one measured and closed with a
smaller fix). Two bugs nobody had listed were also found and fixed. CI is green for the first
time on this branch: pipeline, backend and the new frontend job.

| | Before | After |
|---|---|---|
| Backend tests | 165 | **172 passed** (7 new) |
| Pipeline tests | 159 | **160 passed** (1 new) |
| Frontend lint | 11,470 reports | **0 errors**, 13 warnings |
| `npm audit --omit=dev` | 0 (your fix) | 0, now enforced in CI |
| CI on the branch | red on every run | **green** (3 jobs) |
| Deprecation warnings from our code | dozens | **none** |

## Your changes: verified, and committed as `7a6f8c2`

You couldn't run a browser, so I checked every claim in Chromium against the Docker stack
(Postgres + Garage + API + site behind Caddy). All hold:

- Dark mode: the stylesheet does key on `.dark`; with a dark system, the class is set and
  the background is dark.
- A signed-in admin who opens the sign-in page lands on `/fr/admin`.
- Typing a 6-letter word into the search sends **1** request.
- The mobile drawer opens on the right in Arabic and on the left in French.
- No page errors.
- The dependency update is in place: TanStack Start 1.169.3, 0 vulnerabilities.

**One regression you missed, visible on every search:** in `results.tsx` the condition for the
excerpt row had lost its braces inside `<Fragment>`. React therefore printed
`d.snippets?.length ? (` and `: null}` as text under every result. `tsc` and the build can't
catch this, because it is valid JSX text; only looking at the page shows it. Fixed, and each
excerpt now sits under its own ruling with the search word highlighted.

Also: the theme code read `localStorage` without a guard. It can throw in private mode or when
site data is blocked, and that would break the page. Now guarded.

## 1. Token exposure (high priority): fixed (`06eee22`)

- **Sign-in sets a cookie, `tok_session`:** `HttpOnly`, `SameSite=Lax`, `Secure` over HTTPS.
  Page scripts can't read it; checked in Chromium, where `document.cookie` doesn't show it.
- **The frontend keeps no token.** Nothing is stored in `localStorage` except the email and role
  shown in the interface. Requests use `credentials: "include"`.
- **File links no longer carry a token.** `decisionFileUrl`, `adminFileUrl` and
  `editsExportUrl` are plain addresses, and the cookie goes with the click. So the token can no
  longer leak through logs, history, copied links or the `Referer` header.
- **Protection against cross-site requests:** a POST, PATCH or DELETE authenticated by the
  cookie must come from the site's own origin, or one named in `ALLOW_ORIGINS`. Otherwise it's
  refused with 403.
- **Backward compatible, so nobody is signed out:**
  - the `Authorization` header still works (scripts, tests, pages loaded before the change);
  - `?token=` is still accepted on file links, for old links;
  - a browser that still holds the old token hands it over once (`POST /api/auth/session`),
    receives the cookie for the same session, then deletes the token. Checked in Chromium: such
    a browser stayed signed in and its stored token was gone.
- **Sign-out** ends the session on the server and clears the cookie.
- **CORS** only allows the cookie towards origins named in `ALLOW_ORIGINS`, never `*`.
  `run-local.sh` names its own site address, since there the site and the API are on
  different ports.
- **Tests:** `tests/test_session_cookie.py`, 6 tests. They cover the cookie flags, signing in
  with the cookie alone, a POST without an origin or from another origin refused, the header
  still working from anywhere, a file downloading without a token while an old `?token=` link
  still works, the old token being adopted, and sign-out followed by replaying the cookie
  getting 401.

Not done: single-use signed download URLs. With the cookie they're no longer needed, since no
token appears in any address any more.

## 2. Lint signal: fixed in three separate commits, as you asked

1. **`3423d5c`, line endings only.** `.gitattributes` makes `platform/frontend/**` use LF in
   every checkout, Prettier states `endOfLine: lf`, and the generated route tree is ignored.
   This alone removed **10,176** of the 11,470 reports (Windows checkouts were CRLF).
2. **`9f96f8c`, formatting only:** one `prettier --write` over `src/`, with nothing else in the
   commit. Its hash is in `.git-blame-ignore-revs`
   (`git blame --ignore-revs-file .git-blame-ignore-revs`). Afterwards `tsc`, the build and a
   browser pass over every page were unchanged.
3. **`456d748`, CI:** a new `frontend` job runs `npm ci`, `tsc --noEmit`, `eslint src`
   (Prettier runs inside it; errors fail the job), `npm run build`, and
   `npm audit --omit=dev --audit-level=high`. It also fixes the one real lint error left (an
   `any` for an icon, now `LucideIcon`).

The 13 remaining warnings are all `react-refresh/only-export-components`: files that export
both a component and a helper. They only affect hot reload in development, so I left them as
visible warnings.

### Found while doing it: CI had never been green on this branch (`d05630a`)

The pipeline job failed on every run, in
`test_state_writes_are_throttled_but_nothing_is_lost`, and only on GitHub. **It was a real bug,
not a flaky test.** The pipeline's state file is written at most once per interval, measured
with `time.monotonic()` against a "last save" starting at `0.0`. On Linux, `monotonic()` counts
from boot, and a fresh runner has been up for less than the interval, so the first write was
held back. A machine that has been running for days never shows it. "Never saved" is now its
own case and always writes. The regression test pretends the machine booted 5 s ago, and it
fails without the fix.

## 3. Python 3.13 deprecations: fixed (`9169bc7`)

- **`datetime.utcnow()`, 76 uses:** replaced by `clock.utcnow()`. It returns the same value the
  database stores (UTC, without a time zone), using the API that isn't deprecated.
  - Deliberately **not** converted to time-zone-aware values: every column is
    `TIMESTAMP WITHOUT TIME ZONE` holding UTC. Changing that would mean migrating every
    timestamp in Postgres, with no change in behaviour and some risk.
- **`utcfromtimestamp`** in `logs.py`: replaced.
- **FastAPI's `on_event`:** replaced by a `lifespan`.
- **Alembic:** `path_separator = os` is now set.
- **The pipeline's Vertex code and its tests:** fixed.
- **Remaining warnings, none from our code:**
  - one from Starlette's test client, suggesting `httpx2`;
  - pipeline warnings from **openpyxl** itself, which still calls `utcnow()` even in its latest
    release (3.1.5).

## 4. Bundle weight: measured; one change made (`e3f161a`)

- **First visit: 309 KB compressed in total.** The largest files are the entry (90 KB), the
  translation catalog (43 KB), `AppShell` (35 KB) and the CSS (18 KB).
- **Caching was already right:** every asset is served with
  `Cache-Control: public, max-age=31536000, immutable` and zstd compression, so return visits
  download almost nothing.
- **Splitting the catalog by language:** I chose not to. It would save about 20 KB once per
  reader, against reshaping every string and the type check that relies on them.
- **What did matter, the fonts:** they came from `fonts.googleapis.com` and `fonts.gstatic.com`.
  That meant two more connections before the first paint, and every reader's IP address sent to
  Google, which is also a privacy concern for this site (law 09-08 / CNDP).
  - Inter and IBM Plex Sans Arabic are now bundled: OFL-1.1, `@fontsource` 5.3.0, pinned exactly.
  - Checked in Chromium: the site is the only host contacted, an Arabic page fetches 7 font
    files, and both fonts are ready.
- **Not done:** lazy-loading the CRM code for readers. The CRM pages are already separate
  chunks; only the shared shell loads everywhere.

## 5. Decisions list scalability: fixed (`b40cc56`)

- **Paging:** `/api/decisions` and `/api/search` now take `limit` and `offset`. The page shows
  50 at a time with Previous/Next and "Décisions 51–100", goes back to page 1 when the search or
  a filter changes, and caches each page and filter combination separately, as you suggested.
- **The search had no order,** so pages could repeat or skip rulings. It's now newest first.
- **Request size cap:** `limit` was unbounded, so one request could ask for the whole corpus.
  It's now capped at 200 (1,000 for the admin list); anything larger gets a 422.
- **Search history:** a search is recorded once, not once per page.
- **Checked:** with a test (page 2 shares no ruling with page 1; oversized limits are refused),
  and in Chromium: 1–50, 51–100, and back to 1 after a new search.

## 6. Language and theme flash on first load: fixed (`528e29b`)

- **Language:** the root shell reads the language from the request's own address, so the
  server sends `lang`/`dir` correctly. `/fr` arrives as `fr`/`ltr` and `/ar` as `ar`/`rtl`,
  checked with curl on the HTML the server sends.
- **Theme:** a few lines in `<head>` apply the saved or system theme before the first paint,
  using the same rule as the toggle. Checked in Chromium: with a dark system the page is dark
  when the document is first parsed, and with a light system it isn't. No hydration errors.

## Not deployed

None of this is on the client demo VPS (https://169-58-22-102.sslip.io) yet. Deploying means
rebuilding the images there and about one minute of downtime. Readers stay signed in through
the change: their old token is moved to the cookie automatically.
