#!/usr/bin/env bash
# Start the platform on this machine, against the database already built from
# results/ (29,383 rulings). Nothing here touches the VPS or the pipeline.
#
#   ./run-local.sh          start, print the address and the login
#   ./run-local.sh stop     stop both servers
#
# The database and the Word files live under data/platform/, which is git-ignored.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT=8099
WEB_PORT=5199

export DB_DIR="$ROOT/data/platform"
export FILESTORE_DIR="$ROOT/data/platform/files"
export AUTH_SECRET="${AUTH_SECRET:-local-dev-secret-change-me}"
# The site (5199) forwards /api to the API (8099): one address for the browser, as behind
# Caddy, so the session cookie is first-party whether you open localhost or 127.0.0.1.
export SEED_EMAIL="${SEED_EMAIL:-admin@local}"
export SEED_PASSWORD="${SEED_PASSWORD:-dev-password-1234}"

port_pid () { netstat -ano 2>/dev/null | grep LISTENING | grep ":$1 " | awk '{print $NF}' | head -1; }

stop () {
  for p in "$API_PORT" "$WEB_PORT"; do
    pid="$(port_pid "$p" || true)"
    if [ -n "${pid:-}" ]; then
      taskkill //PID "$pid" //F >/dev/null 2>&1 || kill "$pid" 2>/dev/null || true
      echo "  stopped port $p"
    fi
  done
  if [ -f "$DB_DIR/worker.pid" ]; then
    wpid="$(cat "$DB_DIR/worker.pid")"
    taskkill //PID "$wpid" //F >/dev/null 2>&1 || kill "$wpid" 2>/dev/null || true
    rm -f "$DB_DIR/worker.pid"
    echo "  stopped the worker"
  fi
}

if [ "${1:-}" = "stop" ]; then stop; exit 0; fi

stop
mkdir -p "$DB_DIR"

echo "starting the API on $API_PORT ..."
( cd "$ROOT/platform/backend" \
  && nohup python -m uvicorn server:app --host 127.0.0.1 --port "$API_PORT" \
       > "$DB_DIR/api.log" 2>&1 & )

echo "starting the worker (emails, expiries, reminders, alerts) ..."
( cd "$ROOT/platform/backend"   && { nohup python worker.py > "$DB_DIR/worker.log" 2>&1 & echo $! > "$DB_DIR/worker.pid"; } )

echo "starting the site on $WEB_PORT ..."
( cd "$ROOT/platform/frontend" \
  && VITE_API_URL="" API_PROXY_TARGET="http://127.0.0.1:$API_PORT" nohup npm run dev -- --port "$WEB_PORT" \
       > "$DB_DIR/web.log" 2>&1 & )

for i in $(seq 1 40); do
  sleep 1
  if curl -sf -o /dev/null "http://127.0.0.1:$WEB_PORT/" \
     && curl -s -o /dev/null "http://127.0.0.1:$API_PORT/api/categories"; then
    break
  fi
done

if ! curl -sf -o /dev/null "http://127.0.0.1:$WEB_PORT/"; then
  echo "the site did not come up; see $DB_DIR/web.log" >&2
  exit 1
fi

cat <<EOF

  open        http://127.0.0.1:$WEB_PORT
  email       $SEED_EMAIL
  password    $SEED_PASSWORD

  logs        $DB_DIR/api.log
              $DB_DIR/web.log
              $DB_DIR/worker.log
  stop        ./run-local.sh stop
EOF
