#!/usr/bin/env bash
# CANCELLA il database lab18 (e i suoi allegati) e lo ricrea da zero.
source "$(dirname "$0")/_lib.sh"
read -r -p "Cancello DEFINITIVAMENTE il database $DB. Scrivi SI per confermare: " ok
[ "$ok" = "SI" ] || { echo "Annullato."; exit 0; }
docker compose up -d db
docker compose stop odoo || true
docker compose exec -T db dropdb -U "$POSTGRES_USER" --if-exists "$DB"
docker compose run --rm -T --entrypoint rm odoo -rf "/var/lib/odoo/filestore/$DB"
exec "$(dirname "$0")/init_db.sh"
