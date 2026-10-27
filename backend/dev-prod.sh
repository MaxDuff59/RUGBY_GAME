#!/usr/bin/env bash
# Lance l'API locale avec le catalogue de la prod : le backoffice local modifie le jeu en
# ligne (README, « Retoucher le jeu en ligne depuis le backoffice local »).
#
# Ouvre le tunnel vers le Postgres de Railway (ou reprend celui qui est déjà ouvert),
# lance uvicorn avec backend/.env, et referme le tunnel en quittant (Ctrl+C).
#
# Usage (depuis le dossier backend/) : ./dev-prod.sh  [options d'uvicorn, ex. --port 8001]
set -euo pipefail

PORT=5433
BACKEND="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$BACKEND")"
LOG="$(mktemp -t rugby-tunnel)"

if [[ ! -f "$BACKEND/.env" ]]; then
  echo "Il manque backend/.env (RUGBY_CATALOG_DB_URL vers 127.0.0.1:$PORT)." >&2
  exit 1
fi

open_port() { nc -z 127.0.0.1 "$PORT" 2>/dev/null; }

TUNNEL=""
if open_port; then
  echo "Tunnel déjà ouvert sur le port $PORT : je le reprends."
else
  echo "Ouverture du tunnel vers la base de prod…"
  # Depuis la racine : c'est elle que `railway link` connaît.
  (cd "$ROOT" && exec railway connect Postgres --tunnel-only -P "$PORT") >"$LOG" 2>&1 &
  TUNNEL=$!
  close() {
    pkill -P "$TUNNEL" 2>/dev/null || true
    kill "$TUNNEL" 2>/dev/null || true
    echo "Tunnel fermé."
  }
  trap close EXIT
  for _ in $(seq 1 60); do
    open_port && break
    if ! kill -0 "$TUNNEL" 2>/dev/null; then
      echo "Le tunnel n'a pas pu s'ouvrir :" >&2
      cat "$LOG" >&2
      exit 1
    fi
    sleep 0.5
  done
  if ! open_port; then
    echo "Le tunnel ne répond pas au bout de 30 s :" >&2
    cat "$LOG" >&2
    exit 1
  fi
  echo "Tunnel ouvert : le backoffice écrit dans la base de prod."
fi

cd "$BACKEND"
uv run --env-file .env uvicorn api.main:app --reload "$@"
