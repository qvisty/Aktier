#!/bin/sh
set -e

alembic upgrade head

case "$1" in
  web)
    exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec python -m backend.trading.worker
    ;;
  *)
    exec "$@"
    ;;
esac
