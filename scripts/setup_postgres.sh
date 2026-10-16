#!/usr/bin/env bash
# ==============================================================================
# MEMORA — PostgreSQL Environment Setup Script
# Configures PostgreSQL with pg_stat_statements, pg_buffercache, and pgbench
# ==============================================================================

set -euo pipefail

echo "======================================================================"
echo "          MEMORA: Setting up PostgreSQL for Buffer Cache Validation    "
echo "======================================================================"

DB_NAME="${PGDATABASE:-memora_db}"
DB_USER="${PGUSER:-postgres}"
DB_PORT="${PGPORT:-5432}"

echo "[*] Creating database: ${DB_NAME}..."
createdb -U "${DB_USER}" -p "${DB_PORT}" "${DB_NAME}" || echo "Database already exists or failed to create."

echo "[*] Installing PostgreSQL extensions: pg_stat_statements and pg_buffercache..."
psql -U "${DB_USER}" -p "${DB_PORT}" -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
psql -U "${DB_USER}" -p "${DB_PORT}" -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS pg_buffercache;"

echo "[*] Initializing pgbench benchmark dataset (scale factor 10)..."
pgbench -i -s 10 -U "${DB_USER}" -p "${DB_PORT}" "${DB_NAME}"

echo "[*] Running warm-up pgbench workload (10 clients, 500 transactions)..."
pgbench -c 10 -t 50 -U "${DB_USER}" -p "${DB_PORT}" "${DB_NAME}"

echo "[+] PostgreSQL validation setup completed successfully!"
echo "    Now run MEMORA validation with: python -m memora.postgres.validator"
