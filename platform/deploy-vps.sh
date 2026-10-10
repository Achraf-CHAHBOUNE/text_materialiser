#!/usr/bin/env bash
# Put the platform on a server that is busy with something else.
#
# Run it ON THE SERVER, from /opt/tok/platform:
#     TRANSLATE_API_KEY=... ./deploy-vps.sh 169-58-22-102.sslip.io
#
# It never prunes, never removes an image it did not build, never restarts the Docker
# daemon and never reboots. Everything it starts is pinned to CPU cores 8-11 and named
# under the compose project "tok", so `docker compose -p tok down` removes this and
# nothing else.
set -euo pipefail

SITE="${1:?usage: ./deploy-vps.sh <hostname>}"
CORES="${BUILD_CORES:-}"        # empty: let the scheduler place the build
COMPOSE="docker compose -p tok -f docker-compose.vps.yml"

echo "==> building images (nothing already on this machine is touched)"
docker build ${CORES:+--cpuset-cpus "$CORES"} -t tok-backend:latest ./backend
# Empty API address on purpose: the browser then calls the API on whatever
# address it loaded the page from. Without this the built page asks localhost.
docker build ${CORES:+--cpuset-cpus "$CORES"} --build-arg VITE_API_URL= -t tok-frontend:latest ./frontend

if [ ! -f .env ]; then
    echo "==> writing .env with fresh secrets"
    {
        echo "SITE_ADDRESS=$SITE"
        echo "SITE_URL=https://$SITE"
        echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
        echo "AUTH_SECRET=$(openssl rand -hex 32)"
        echo "AUTH_TTL_SECONDS=86400"
        echo "SEED_EMAIL=admin@jurismaroc.local"
        echo "SEED_PASSWORD=$(openssl rand -base64 12 | tr -d '/+=' | cut -c1-14)"
        [ -n "${TRANSLATE_API_KEY:-}" ] && echo "TRANSLATE_API_KEY=$TRANSLATE_API_KEY"
    } > .env
    chmod 600 .env
fi
# The key is added to an existing .env too, so re-running can switch translation on.
if [ -n "${TRANSLATE_API_KEY:-}" ] && ! grep -q "^TRANSLATE_API_KEY=" .env; then
    echo "TRANSLATE_API_KEY=$TRANSLATE_API_KEY" >> .env
fi

echo "==> starting (postgres, backend, frontend, proxy) on cores 8-11"
$COMPOSE up -d

echo "==> waiting for the site to answer"
for _ in $(seq 1 60); do
    curl -sf -o /dev/null "http://127.0.0.1/health" && break || sleep 3
done

if [ -d incoming/results ]; then
    echo "==> importing the rulings (this is the long part)"
    $COMPOSE exec -T backend python import_results.py /incoming/results --actor setup --workers 2
fi

echo
echo "================= ready ================="
echo "  https://$SITE"
echo "  admin: $(grep '^SEED_EMAIL=' .env | cut -d= -f2)  /  $(grep '^SEED_PASSWORD=' .env | cut -d= -f2)"
grep -q '^TRANSLATE_API_KEY=' .env && echo "  French translation: on" || echo "  French translation: off (no key)"
echo "  stop it with:  docker compose -p tok -f docker-compose.vps.yml down"
echo "========================================="
