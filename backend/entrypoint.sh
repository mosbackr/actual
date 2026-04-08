#!/bin/sh
set -e

# If DB components are provided (AWS deployment), construct DATABASE_URL
if [ -n "$DB_HOST" ] && [ -n "$DB_PASSWORD" ]; then
  DB_USER="${DB_USER:-acutal}"
  DB_NAME="${DB_NAME:-acutal}"
  DB_PORT="${DB_PORT:-5432}"
  export ACUTAL_DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
fi

exec "$@"
