# The platform as a business: languages, customers, sales, billing

This is the part of the platform that turns a corpus into a service people pay for:
the site in Arabic and in French, customer accounts with seats, the contracts and bank
transfers that open them, the CRM the team follows readers and money with, support, and
a reader's own library.

It is one application -- a modular monolith -- not a set of services: one FastAPI
backend split into modules, one Postgres database, one background worker.

```
backend/
  accounts.py   organizations, sessions, invitations, password reset, two-factor
  contracts.py  a client's contracts (signed PDF) and bank transfers (proof) -- what opens access
  billing.py    plans, subscriptions, invoices (optional, made from a transfer), payments
  crm.py        the public request inbox, clients (organizations) and their health
  insights.py   what each reader reads, downloads, searches and for how long; alerts; the dashboard
  support.py    tickets and their messages
  library.py    folders and notes, alerts, history, reading time, download quotas and marks
  mailer.py     every email, in the reader's language, through one outbox
  worker.py     what happens without anyone asking (emails, expiries, reminders, the admin digest)
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
| `sales` | the team | the CRM: clients, contracts, transfers, readers, tickets |
| `client_admin` | a customer's account holder | read, and invite or remove colleagues within the seats paid for |
| `client` | a customer's reader | read, save, download within the quota, alerts, support |

A customer's people read **only while their organization has a paid, running contract**.
When it lapses, the rulings close (HTTP 402) but their account, invoices and support
stay open, so they can see why and put it right. The site shows one banner, not a
page of errors.

**Sessions** are rows, not just signed tokens: signing out ends one, a password change
or reset ends the others, and a reader signing in on a second device ends the first --
one seat is one person at a time. Staff may use several devices.

**Two-factor** sign-in (the six-digit codes of Google or Microsoft Authenticator) is
on the account page for everyone; staff without it are reminded on every visit.

---

## The CRM: for us alone

Readers have a reading space and nothing else; they never see any of this. The CRM
follows the way a client actually arrives in Morocco:

```
the client pays by bank transfer (virement) --> a contract is signed --> we open the accounts
```

Tabs: **Tableau de bord · Clients · Utilisateurs · Usage · Alertes · Contrats et
paiements · Assistance**, and the **Nouveau client** button.

### Nouveau client

One page, four steps, one save (`POST /api/crm/clients`):

1. **The client** -- a person or a firm, ICE, contact details, the language of its emails.
2. **The contract** -- plan, number of accounts, dates, price HT and VAT; the signed PDF
   attached. Numbered `C-2026-0001`.
3. **The transfer** -- amount TTC, date, bank, reference, the proof attached; or *not
   yet*.
4. **The accounts** -- one email per seat, at most the seats of the contract (checked
   before anything is created). Each person is emailed to choose a password.

With a transfer the accounts open at once, over the contract's dates. Without one they
are created but stay closed (HTTP 402) until the first transfer is recorded on the
contract -- then they open by themselves.

A request from the public page (`/pricing`, rate-limited, with a hidden field that
catches robots) lands in the dashboard's inbox; *Créer le client* opens this page
already filled in, and the request is marked converted only once the client is saved.

### Contrats et paiements

Every contract with its status -- *awaiting transfer*, *upcoming*, *running*, *ended*,
*cancelled* -- what it costs, what was received, what is still owed, and whether the
signed PDF is on file; filters for awaiting, running, ending within 30 days, owing,
ended. Every transfer with its bank, reference and proof.

- **Renewal** is a new contract from the client's page; it starts the day after the
  current one ends and opens access when its transfer is recorded.
- **Part transfers** are fine; the balance is shown until it reaches zero.
- **An invoice is optional**: *Faire la facture* turns a transfer into a paid invoice
  (`F-2026-00001`), once; the money is never counted twice.
- A contract with no transfer can be cancelled; one that was paid cannot.

### Following the readers

`insights.py` reads back what the platform already records -- every view, search,
download, translation and sign-in, each session's address and device, each download's
reference, and the time spent on each ruling and in which language (a beat every 30
seconds while the page is visible, staff ignored).

| page | what it answers |
|---|---|
| **Tableau de bord** | readers (active today, this week, this month), money received this month and year, what is owed, contracts running and ending, the alerts, activity per day, most read rulings, the request inbox |
| **Clients** | each client: contract and dates, accounts used of those paid for, paid and owed, health. One client: contracts and transfers, accounts (invite, change role, suspend), details, history |
| **Utilisateurs** | every reader: plan and until when, reads, reading time and share in French, downloads, searches, paid and owed, last activity, signed in now or not |
| **one reader** | everything they did, newest first; reading time and the rulings read longest; team notes; an email written from the page (kept as a note); activity per day; chambers; downloads with their reference; devices and addresses; contracts and invoices. Actions: renew, suspend, sign out everywhere, export |
| **Usage** | the platform over 7 to 365 days, most read and downloaded rulings, searches -- and **searches that found nothing** |
| **Alertes** | the serious first: an account used from 3+ addresses in a day (shared), 3+ devices in a week, the download limit reached, reading at a pace no person reads at, a paying reader silent for 15 days, contracts awaiting their transfer, ending within 30 days, or with money still owed |

**Find a file**: under the tabs, type the reference printed at the foot of a Word file
found circulating -- the page names who downloaded it, when, and which ruling.

**Health** is read from what the client's people do: *active* (20+ actions in 30
days), *new* (a client of less than 30 days), *quiet*, or *at risk* (nobody opened
anything in 30 days).

**One figure for money.** What is received and what is owed are counted once, the same
way on every page: transfers, plus the payments and unpaid balances of invoices made
before contracts existed. Every centime owed appears in an alert -- a contract awaiting
its transfer, or a balance.

Everything exports to CSV for Excel, for one reader or for all. Nothing is deleted:
records are marked, so history and figures stay true.

**Removed**, because they were not how the business works: the prospect pipeline,
tasks, quotes, the reports page (its figures are on the dashboard), the sales digest,
and the firm module (cabinet).

---

## Billing

- **Plans** (`trial`, `individual`, `firm`, `institution`) are seeded once as
  *examples*. Set the real names, prices, seats and download quotas in
  *Administration › Offres et prix* before launch.
- **Subscriptions** are opened by contracts (see above): a renewal starts the day after
  the current one ends, so no day is lost or paid twice.
- **Invoices** are numbered `F-2026-00001`, `F-2026-00002`... per year, without gaps or
  repeats (the number is unique in the database). VAT 20%. An issued invoice is
  cancelled, never deleted. Each has a printable page; the browser's *print to PDF*
  makes the file. Seller details come from `SELLER_*` settings.
- **Money comes in as transfers** recorded on contracts. An invoice is made from a
  transfer only when the client asks for one. Older invoices and their payments still
  count in what was received and what is owed.
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
| once a day | end the subscriptions past their last day · mark unpaid invoices overdue · remind customers 30, 15 and 7 days before the end (once each) · send the readers' saved-search alerts · email the admins their digest: new readers and transfers of the day before, contracts ending (30/15/7/1 days), contracts awaiting their transfer, serious alerts |

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

`test_business.py` follows the business the way it is used -- a request reaches the
inbox, a client is created with its contract and transfer and its people read; without
a transfer they are refused until it is recorded; too many accounts are refused before
anything is made; a transfer becomes an invoice once and is counted once; a renewal; the
dashboard adds up. `test_insights.py` covers the readers: activity, find-a-file, reading
time, notes and emails, the shared-account alert. `test_bilingual.py` covers the French
site. They run on SQLite, and on Postgres with `DATABASE_URL` set.
