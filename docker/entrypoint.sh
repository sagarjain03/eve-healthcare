#!/bin/sh
# Container start: apply migrations, optionally seed demo data, then run gunicorn.
set -e

python manage.py migrate --noinput

if [ "${SEED_ON_START:-false}" = "true" ]; then
    python manage.py seed_data
fi

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --access-logfile -
