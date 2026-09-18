# Putting the demo online, temporarily and for free

For showing the platform to a colleague or a manager before anything is decided about
real hosting. All of it is reversible: nothing here is a deployment.

Everything below serves the **demo pack** (60 anonymized rulings built by
`scripts/make_demo.py`), never the full delivery.

## Before you put it anywhere

The demo holds real rulings. They are anonymized and passed the leak check, but they
are still the client's documents on somebody else's computer. So:

- **ask the client first** if the link will live longer than a meeting;
- **change the demo passwords** from the ones in `docker-compose.demo.yml` — they are
  published in this repository;
- the site already tells search engines not to list it, and nothing is readable
  without signing in;
- **take it down** when the review is over.

If that is not comfortable, the honest alternative is to demo by screen share, which
puts nothing online at all.

## The site and the API share one address

`docker-compose.demo.yml` runs a small proxy: the site is on `:8080` and the API is on
`:8080/api/...`, so a tunnel or a host only has to expose one port, the browser calls
the API on whatever address it loaded the page from, and there is no cross-origin
setup and no URL baked into the build.

## 1. A tunnel from your own machine — minutes, no account

Best for a call, or a day or two of review. Nothing is hosted: a temporary public
address forwards to the demo running on your machine, and disappears when you stop it.
Your machine has to stay on and awake.

```bash
cd platform
docker compose -f docker-compose.demo.yml up -d      # the demo on :8080
cloudflared tunnel --url http://localhost:8080       # prints a https://….trycloudflare.com address
```

`cloudflared` is a single executable from Cloudflare — no account for this mode. On
Windows: `winget install --id Cloudflare.cloudflared`. Ctrl+C ends the tunnel and the
address stops working immediately.

Anyone with the address reaches the sign-in page, so treat it as public and change the
demo passwords first.

## 2. A free host — the link keeps working when your machine is off

For a manager who will open it on their own time. Free tiers put the service to sleep
when it is idle, so the first visit after a pause takes a minute to wake; after that it
is normal speed. Free tiers also give no permanent disk: the demo rebuilds itself from
the pack on every start, so any correction made *in the demo* is lost on restart. That
is fine for a demo and worth saying out loud before someone tries it.

Anything that runs a Docker image works. Two that are free and take a repository
directly: **Render** and **Koyeb**. Both want one container per service, and the demo
is three (site, API, proxy), so either run the three as separate services and point the
site at the API's address, or push a single combined image. Neither is a five-minute
job — if the link needs to live for weeks, a small paid server (a few dollars a month)
is simpler than fighting the free tiers, and it is the same `docker compose up`.

## 3. A free virtual machine — closest to the real thing

Oracle Cloud's Always Free tier includes a small permanent VM. It runs the compose
files as they are, keeps its data between restarts, and never sleeps. Signing up needs
a card for identity checks, and the setup is the usual server work: create the machine,
install Docker, copy the repository and the demo pack, open the port, add a domain and
a certificate.

## When the decision is made

Real hosting uses `docker-compose.yml`, not the demo file: Postgres instead of a file
database, object storage for the documents, your own keys, and the full delivery
imported with `python import_results.py ../../results`. See the main README.
