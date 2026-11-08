#!/usr/bin/env bash
# Crea il database lab18 con dati demo e installa tutti i moduli del flusso.
source "$(dirname "$0")/_lib.sh"
docker compose up -d --wait db
# Già installato? (un db vuoto creato da Odoo all'avvio NON conta come installato)
if docker compose exec -T db psql -U "$POSTGRES_USER" -d "$DB" -Atc \
     "select 1 from ir_module_module where name='lab_workflow_custom' and state='installed'" \
     2>/dev/null | grep -q 1; then
  echo "Il database $DB è già installato: non reinstallo nulla (per ripartire da zero: ./scripts/reset_db.sh)."
  docker compose up -d odoo
  exit 0
fi
docker compose stop odoo || true
echo "Creo $DB con dati demo e installo: $MODULES (qualche minuto...)"
odoo_run -d "$DB" -i "$MODULES" --load-language=it_IT
set_passwords
docker compose up -d odoo
echo "Fatto. Apri http://127.0.0.1:8069  (utente: admin, password: LAB_ADMIN_PASSWORD in .env)"
