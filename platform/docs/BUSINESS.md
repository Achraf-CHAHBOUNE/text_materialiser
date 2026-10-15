# The platform as a business: languages, customers, sales, billing

This is the part of the platform that turns a corpus into a service people pay for:
the site in Arabic and in French, customer accounts with seats and subscriptions, the
CRM the team sells and renews with, invoices, support, and a reader's own library.

It is one application -- a modular monolith -- not a set of services: one FastAPI
backend split into modules, one Postgres database, one background worker.

```
backend/
  accounts.py   organizations, sessions, invitations, password reset, two-factor
  billing.py    plans, subscriptions, invoices, payments
  crm.py        leads, contacts, opportunities, activities, tasks, dashboard
  sales.py      quotes, email from the CRM, revenue reports, CSV in and out, duplicates
  insights.py   what each reader reads, downloads and searches, what they pay -- for us
  practice.py   the firm module (switched off): a law firm's own cases, hearings, fees
  support.py    tickets and their messages
  library.py    folders and notes, alerts, history, download quotas and marks
  mailer.py     every email, in the reader's language, through one outbox
  worker.py     what happens without anyone asking (emails, expiries, reminders, alerts)
  deps.py       who is asking and what they may do -- every module's guards
```

---

## Two languages

Every page lives at `/ar/...` and `/fr/...`. The prefix *is* the language: a link opens
in the language it was shared in, the server renders the right one first time, and the
switch keeps the reader on the same page. An address with no prefix gets the reader's
last choice, else Arabic.

| | Arabic | French |
|---|---|---|
| menus, labels, emails | Arabic | French |
| ruling text | the court's Arabic | machine translation, the Arabic one click away (alone or side by side) |
| abstract, subject, keywords, outcome | Arabic | French, each labelled as a translation |
| search | the Arabic text | the French text (accents ignored); an Arabic query still searches the Arabic |

Rules that do not bend: the Arabic is the text that counts, and the page says so;
the court's own rule translated is labelled *Traduction automatique de la règle de la
Cour*, never passed off as the court's words; a ruling with no French yet is shown in
Arabic with *Traduction non disponible*, never as an empty page.

The French lives in `decision_i18n` (one row per ruling per language) and `subjects`
(each subject's French name). Two scripts fill them:

```bash
cd platform/scripts
python migrate_i18n.py --delivery ../../delivery   # the French already made, free
python translate_labels.py                         # subjects and keyword chains, ~$0.15
```

---

## Who does what

| role | who | may |
|---|---|---|
| `admin` | you | everything: staff accounts, plans and prices, emails, plus all below |
| `editor` | the team | the rulings: import, correct, publish, error reports |
| `sales` | the team | the CRM: leads, organizations, subscriptions, invoices, tickets |
| `client_admin` | a customer's account holder | read, and invite or remove colleagues within the seats paid for |
| `client` | a customer's reader | read, save, download within the quota, alerts, support |

A customer's people read **only while their organization has a running subscription**.
When it lapses, the rulings close (HTTP 402) but their account, invoices and support
stay open, so they can see why and put it right. The site shows one banner, not a
page of errors.

**Sessions** are rows, not just signed tokens: signing out ends one, a password change
or reset ends the others, and a reader signing in on a second device ends the first --
one seat is one person at a time. Staff may use several devices.

**Two-factor** sign-in (the six-digit codes of Google or Microsoft Authenticator) is
on the account page for everyone; staff without it are reminded on every visit.

---

## Selling: the CRM

```
demo form (public) ──► lead ──convert──► organization + contact + opportunity
                                          + 14-day trial + invitation emailed
opportunity: new → contacted → demo → trial → won | lost
```

- **Leads** come from the public page (`/pricing`, rate-limited, with a hidden field
  that catches robots) or are entered by hand. *Convert* does the rest in one click.
- **Organizations** carry their contacts, their people's accounts, subscriptions,
  invoices, activities (calls, emails, meetings, notes), tasks, opportunities, and the
  full audit trail of who changed what.
- **Health** is read from what the organization's people actually do: *active* (20+
  actions in 30 days), *quiet*, or *at risk* (nobody opened anything in 30 days, and
  the customer is older than 30 days).
- **The dashboard** shows new leads, revenue this month, what is left to collect, the
  pipeline, renewals in the next 30 days and customers at risk.

Nothing in the CRM is deleted: records are marked, so history and figures stay true.

**Going further** (`sales.py`):

- **Quotes (devis)** `D-2026-00001`: from a plan (monthly price × months) or with custom
  lines, valid 30 days, printable, emailed to the organization. *Accept* does everything
  at once: the subscription at the quoted price (it starts after the current paid one,
  or at once during a trial), the invoice, the opportunity won, the organization a
  customer. A quote is accepted once.
- **Email from the CRM**: written on the organization's page, sent through the outbox,
  kept in its history.
- **Reports**: MRR (what active customers pay a month, negotiated price when there is
  one), ARR, average per customer, cash collected month by month over 12 months, new
  customers and departures, lead conversion, win rate, and the open pipeline weighted
  by stage (new 10% → trial 60%).
- **Lists in and out**: CSV exports for Excel (leads, organizations, invoices,
  payments); a CSV import of leads that skips anyone already known, so importing the
  same bar-association list twice is harmless; a warning when a new lead looks like
  an existing lead or organization.
- **Each sales person's day** by email: tasks due, renewals they manage.

---

## Following the readers (admin only)

The CRM is ours: readers have a reading space and nothing else, and never see any of
this. `insights.py` reads back what the platform already records -- every view,
search, download, translation and sign-in (`client_activity`), each session's address
and device, each download's reference -- for admin and sales.

| page | what it answers |
|---|---|
| **CRM › Utilisateurs** | every reader: organization, plan and until when, reads, downloads and searches over 30 days, total read, what their organization has paid and still owes, last activity, signed in now or not. Filters: active, idle, subscription ended, owing; sorts by activity, reads, downloads, money |
| **one reader** | everything they did, newest first (each ruling by number and chamber, each search with its words, *no result* marked); activity per day; the chambers they read most; downloads with the reference printed in the file; devices and IP addresses of each sign-in; invoices and payments. Actions: suspend, sign out everywhere, export their activity |
| **CRM › Usage** | the platform over 7 to 365 days: active readers, reads, downloads, searches, sign-ins per day; most read and most downloaded rulings (times, distinct readers); most frequent searches; **searches that found nothing** -- what the corpus is missing; the most active readers |

Everything exports to CSV for Excel, for one reader or for all.

---

## The firm module (cabinet) -- switched off

Built, tested, and **off**: readers have a reading space only. Every plan comes with it
switched off; an administrator could turn it on per plan (*Administration › Offres et
prix*) if that is ever wanted. What follows describes it for that day.

### What it is

What makes a firm open the platform every day, not only when it researches: its own
clients and cases, in the same place as the case law. `practice.py`, at `/cabinet`.

| | |
|---|---|
| **Clients** | people and companies the firm represents: identity (CIN / RC, ICE), contact details, notes |
| **Cases** (dossiers) | the firm's own reference `2026/0001`, client and their role, opposing party and lawyer, court, chamber, level, court file number, nature, responsible lawyer, fee agreement, status |
| **Hearings** | date, time, room, purpose; recording the outcome can schedule the next hearing in the same step |
| **Deadlines** | opposition, appeal, cassation... computed from the notification date, moved to the next working day when they fall on a weekend, and marked *to verify* until a lawyer confirms them |
| **Tasks** | per case or general, assigned to a member |
| **Documents** | per case, 20 MB each, private to the firm |
| **Time and expenses** | hours at a rate, court fees, bailiff, expert... |
| **Fee notes** | numbered per firm `2026-0001`, built from the case's unbilled time and expenses plus any fixed fee, VAT 10% (editable), part payments, printable; cancelling one makes its lines billable again |
| **Case law** | rulings from the corpus tied to a case from the ruling's own page, with a note |
| **Agenda and dashboard** | hearings, deadlines and tasks by day (late ones first), for the firm or for me; what is unpaid, what was collected this month |
| **Daily email** | each lawyer: their hearings within two days and deadlines within seven, unverified ones flagged |

**This module holds real personal data**, unlike the rest of the platform. So:

1. **A firm sees only itself.** The firm is always the signed-in person's organization,
   never a value from the request; every query filters on it.
2. **Our own staff cannot read it** -- admin, sales and editors alike are refused. The
   firm is the data controller; we only process its data (law 09-08).
3. **Erasing is real.** The account holder can erase a client: every case, hearing,
   deadline, document *file*, time entry and fee note under it is deleted, not flagged.
4. **The audit trail keeps ids, never names** -- otherwise it would become a second copy
   of the firm's client list.

Whether a plan includes the module is a switch on the plan (*Administration › Offres et
prix*); it is off on every plan.

**A deadline is the lawyer's responsibility.** The presets (opposition 10 days, appeal
30, criminal appeal 10, cassation 30) are the usual ones; public holidays are not
counted; a deadline stays *to verify* until someone confirms it, and the page says so.

---

## Billing

- **Plans** (`trial`, `individual`, `firm`, `institution`) are seeded once as
  *examples*. Set the real names, prices, seats and download quotas in
  *Administration › Offres et prix* before launch.
- **Subscriptions**: a renewal starts the day after the current one ends, so no day is
  lost or paid twice.
- **Invoices** are numbered `F-2026-00001`, `F-2026-00002`... per year, without gaps or
  repeats (the number is unique in the database). VAT 20%. An issued invoice is
  cancelled, never deleted. Each has a printable page; the browser's *print to PDF*
  makes the file. Seller details come from `SELLER_*` settings.
- **Payments** are recorded by staff: transfer, cheque, cash, card at the desk. Part
  payments are fine; the invoice turns *paid* when the balance reaches zero.
- **Online card payment is not built**: it needs a merchant contract with a Moroccan
  bank (CMI). The invoice model is ready for it.

Money is held in centimes, as whole numbers. Nothing is rounded twice.

---

## A reader's own space

- **Folders** with a note per ruling. A folder can be shared with the whole firm.
- **Alerts**: a search saved from the listing (*Créer une alerte*); the worker emails
  what was published since the last one, daily or weekly, in the alert's language.
- **History**: what they read, searched and downloaded.
- **Downloads** are counted and limited per day by the plan, and each Word file carries
  at the foot of every page who downloaded it, when, and a reference that leads back
  to the record -- a file passed around can be traced. Reading at a pace no person
  reads at (300 rulings an hour) is refused.
- **Support**: tickets, seen by everyone in the firm and by the team; replies are
  emailed.

---

## The worker

```bash
python worker.py          # forever, beside the API (docker compose runs it as `worker`)
python worker.py --once   # one pass, then exit
```

| every minute | send the emails waiting in the outbox |
| once a day | end the subscriptions past their last day · mark unpaid invoices overdue · remind customers and their account manager 30, 15 and 7 days before the end (once each) · send the alerts |

Without `SMTP_HOST`, emails wait in the outbox and *Administration › E-mails* shows
them -- a fresh install works, nothing is lost.

---

## Settings

All in `platform/.env`, documented in `.env.example`:

| | |
|---|---|
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_FROM` `SMTP_TLS` | sending email |
| `SITE_URL` | where links in emails point |
| `SELLER_NAME` `SELLER_ADDRESS` `SELLER_ICE` `SELLER_RIB` | printed on invoices |
| `WORKER_INTERVAL` | seconds between the worker's passes (60) |

---

## Upgrading a database that already serves

Nothing needs to be run by hand for the structure: on startup the API creates the new
tables, adds the new columns to `users`, seeds the example plans, and gives every
existing customer account an organization of its own with a year's subscription -- so
nobody loses access. Existing tokens stop working once; everyone signs in again.

The French content is data, not structure, and is carried over without paying for it
twice:

```bash
# on the machine that has it
python sync_enrichment.py export enrichment.jsonl.gz
# on the server, after copying the file there
python sync_enrichment.py apply enrichment.jsonl.gz
```

On Postgres, the French word index is a stored column; on a table that is still
empty it is created instantly at startup, so apply the file after the upgrade, not
before.

---

## Tests

```bash
cd platform/backend && python -m pytest tests/ -q
```

`test_business.py` follows the business the way it is used -- a demo request becomes a
customer, its people are invited and read within what they pay for, the team is paid
-- and `test_bilingual.py` the French site. Both pass on SQLite and on Postgres.
`test_crm_deep.py` covers quotes, reports, import and export, and above all the firm
module's walls: one firm cannot see another, our staff see nothing, erasing removes the
files, the audit trail holds no names. The isolation rules are mutation-checked.
