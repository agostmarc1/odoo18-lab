#!/usr/bin/env bash
# Crea il database lab18 con dati demo e installa tutti i moduli del flusso.
source "$(dirname "$0")/_lib.sh"
docker compose up -d db
docker compose stop odoo || true
echo "Creo $DB con dati demo e installo: $MODULES (qualche minuto...)"
odoo_run -d "$DB" -i "$MODULES" --load-language=it_IT
set_passwords
docker compose up -d odoo
echo "Fatto. Apri http://127.0.0.1:8069  (utente: admin, password: LAB_ADMIN_PASSWORD in .env)"
